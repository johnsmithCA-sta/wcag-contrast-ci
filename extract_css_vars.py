#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_css_vars.py —— CSS 变量（自定义属性）批量提取与 Token 表核对工具
（设计评估工具链 · 检查工具组）

用途：
  1. 从单个 CSS 文件或目录（递归 *.css）提取 --var 定义，按类别分组：
     颜色类（#hex / rgb() / rgba() / hsl()）、字号类（px/rem/em）、
     间距/圆角类、其他类；
  2. 统计每个变量的 var() 引用次数（含 fallback），引用次数低于 --min-usage
     的变量标注"低频"；
  3. 扫描未用 var() 包装的散落硬编码色值（#hex、rgb() 等），输出
     "行号: 声明 | 色值"，用于识别 token 化残留（对标 references/checkpoints.md Token 节「Token 可核对」）；
  4. 可选传入 --token-table JSON 做核对：
     a. R4「同语义同色值」：同名变量异值 / token 表同值异名 /
        同一规则内多个硬编码色值（疑似同语义双色值）/
        token 已 var() 引用但其值仍以硬编码并存；
     b. 死 Token：表中定义但源码从未 var() 引用；
     c. 可替换硬编码：与 token 值相同但未走 var() 的散落色值，提示可替换为 var(--x)。

示例命令：
  python3 extract_css_vars.py --input styles.css
  python3 extract_css_vars.py --input styles/ --token-table tokens.json
  python3 extract_css_vars.py --input styles/ --token-table tokens.json --json out.json --min-usage 3

参数：
  --input       必填：CSS 文件路径或目录（目录递归查找 *.css）
  --token-table 可选：Token 表 JSON 路径，格式 {"primary":"#0e9f8e", ...}
  --json        可选：完整结果 JSON 输出路径（stdout 仍打印 Markdown 表格）
  --min-usage   可选：引用次数低于该值的变量标注"低频"（默认 2；<=0 关闭该标注）

仅使用 Python 标准库（re/json/argparse/os/sys），无第三方依赖。
"""

import argparse
import json
import os
import re
import sys

# ---------------- 正则 ----------------
# 颜色字面量：#hex / rgb() / rgba() / hsl() / hsla()
COLOR_RE = re.compile(r'#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)', re.IGNORECASE)
# 变量定义：--name: value;（value 可缺省结尾分号，如块内最后一项）
VAR_DEF_RE = re.compile(r'(--[\w-]+)\s*:\s*([^;{}]+?)\s*(?:;|(?=\s*[}]))')
# 变量引用：var(--name)（可能带 fallback，只取变量名）
VAR_USE_RE = re.compile(r'var\(\s*(--[\w-]+)')
# 字号单位（px/rem/em）
FONT_UNIT_RE = re.compile(r'[\d.]+\s*(?:px|rem|em)')


def strip_comments(css: str) -> str:
    """把 /* ... */ 注释替换为等量换行，保持行号不变，便于后续按行定位。"""
    return re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group(0).count('\n'), css, flags=re.S)


def line_of(text: str, pos: int) -> int:
    """由字符偏移换算行号（1 起）。"""
    return text.count('\n', 0, pos) + 1


def decl_text(text: str, pos: int) -> str:
    """取色值所在行的整行内容（去首尾空白），作为"声明"展示。"""
    ls = text.rfind('\n', 0, pos) + 1
    le = text.find('\n', pos)
    if le == -1:
        le = len(text)
    return text[ls:le].strip()


def find_var_spans(text: str):
    """找出所有 var( ... ) 的 (start, end) 区间（支持嵌套括号与 fallback）。"""
    spans, i, n = [], 0, len(text)
    while True:
        j = text.find('var(', i)
        if j == -1:
            break
        k, depth = j + 4, 1
        while k < n and depth > 0:
            if text[k] == '(':
                depth += 1
            elif text[k] == ')':
                depth -= 1
            k += 1
        spans.append((j, k))
        i = k
    return spans


def find_blocks(text: str):
    """找出所有 { ... } 块（含嵌套）→ [(selector, start, end)]。"""
    blocks, stack, sel_start = [], [], 0
    for i, ch in enumerate(text):
        if ch == '{':
            stack.append((i + 1, text[sel_start:i].strip()))
            sel_start = i + 1
        elif ch == '}':
            if stack:
                s, sel = stack.pop()
                blocks.append((sel, s, i))
            sel_start = i + 1
    return blocks


def classify(name: str, value: str) -> str:
    """按值（辅以名称语义）将变量归类：颜色类 / 字号类 / 间距圆角类 / 其他类。"""
    v = value.strip().lower()
    if re.match(r'^#[\da-f]{3,8}\b|^rgba?\(|^hsla?\(', v):
        return '颜色类'
    if FONT_UNIT_RE.fullmatch(v):
        if re.search(r'font|size|text', name):
            return '字号类'
        return '间距/圆角类'
    return '其他类'


def innermost_block(blocks, pos):
    """返回包含 pos 的最内层块下标（区间最小者），无则 None。"""
    best = None
    for i, (_sel, s, e) in enumerate(blocks):
        if s <= pos < e:
            if best is None or (e - s) < (blocks[best][2] - blocks[best][1]):
                best = i
    return best


def extract_file(path: str):
    """解析单个 CSS 文件：返回 {'defs','uses','hardcoded'}。"""
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        raw = f.read()
    clean = strip_comments(raw)
    var_spans = find_var_spans(clean)
    blocks = find_blocks(clean)

    defs = []
    for m in VAR_DEF_RE.finditer(clean):
        name, value = m.group(1), m.group(2).strip()
        if not value:
            continue
        defs.append({'name': name, 'value': value, 'category': classify(name, value),
                     'line': line_of(clean, m.start()),
                     'start': m.start(), 'end': m.end()})

    uses = {}
    for m in VAR_USE_RE.finditer(clean):
        uses[m.group(1)] = uses.get(m.group(1), 0) + 1

    hardcoded = []
    for m in COLOR_RE.finditer(clean):
        pos = m.start()
        # 排除 var() 内部的色值（含 fallback）
        if any(s <= pos < e for s, e in var_spans):
            continue
        # 排除变量定义值本身（那是 token 定义，不是散落硬编码）
        if any(d['start'] <= pos < d['end'] for d in defs):
            continue
        bi = innermost_block(blocks, pos)
        hardcoded.append({'line': line_of(clean, pos), 'decl': decl_text(clean, pos),
                          'color': m.group(0),
                          'block': blocks[bi][0] if bi is not None else None})
    return {'defs': defs, 'uses': uses, 'hardcoded': hardcoded}


def tok_name(k):
    """Token 表 key 归一化为 CSS 变量名（补 '--' 前缀）。"""
    return k if k.startswith('--') else '--' + k


def check_token_table(all_defs, all_uses, all_hard, tokens):
    """Token 表核对：R4 同语义同色值 / 死 token / 可替换硬编码。"""
    r4, dead, replacable = [], [], []

    # a1) 同名变量多处定义且值不同
    by_name = {}
    for d in all_defs:
        by_name.setdefault(d['name'], set()).add(d['value'])
    for name, vals in sorted(by_name.items()):
        if len(vals) > 1:
            r4.append(f"[同名异值] 变量 `{name}` 在不同位置定义了不同值：{', '.join(sorted(vals))}")

    # a2) token 表内同值异名
    by_val = {}
    for k, v in tokens.items():
        by_val.setdefault(v.strip().lower(), []).append(k)
    for v, keys in sorted(by_val.items()):
        if len(keys) > 1:
            r4.append(f"[同值异名] token 表中 {' / '.join('`'+k+'`' for k in keys)} 均为同一色值 {v}")

    # a3) 同一规则内多个不同硬编码色值（疑似同语义双色值）
    by_block = {}
    for h in all_hard:
        by_block.setdefault((h['file'], h['block']), set()).add(h['color'].lower())
    for (f, blk), colors in sorted(by_block.items()):
        if blk and len(colors) > 1:
            r4.append(f"[同语义双色值] 规则 `{blk}`（{os.path.basename(f)}）内并存 "
                      f"{len(colors)} 个不同硬编码色值：{', '.join(sorted(colors))} "
                      f"—— 疑似同一语义色值未统一，建议 token 化")

    # a4) token 既经 var() 引用、其值又以硬编码形式并存
    hard_vals = {h['color'].lower() for h in all_hard}
    for k, v in sorted(tokens.items()):
        if all_uses.get(tok_name(k), 0) > 0 and v.strip().lower() in hard_vals:
            r4.append(f"[引用不一致] token `{k}` 已通过 var() 引用，但其值 {v} 仍以硬编码形式出现在源码中")

    # b) 死 token（表中定义但源码从未引用）
    for k, v in sorted(tokens.items()):
        if all_uses.get(tok_name(k), 0) == 0:
            defined = any(d['name'] == tok_name(k) for d in all_defs)
            dead.append({'token': k, 'value': v, 'defined_in_source': defined,
                         'note': '源码中定义了该变量但从未引用' if defined else '源码中无任何定义或引用'})

    # c) 可替换硬编码（与 token 值相同但未走 var()）
    for h in all_hard:
        hits = [k for k, v in tokens.items() if v.strip().lower() == h['color'].lower()]
        if hits:
            replacable.append({'line': h['line'], 'file': os.path.basename(h['file']),
                               'color': h['color'],
                               'suggest': [f"var(--{k})" for k in sorted(hits)]})

    return {'r4': r4, 'dead': dead, 'replacable': replacable}


def build_report(input_path, file_results, min_usage, tokens):
    """汇总各文件结果，构造最终报告 dict。"""
    all_defs, all_hard = [], []
    all_uses = {}
    for fr in file_results:
        for d in fr['defs']:
            all_defs.append({**{k: d[k] for k in ('name', 'value', 'category', 'line')},
                             'file': os.path.basename(fr['file'])})
        for h in fr['hardcoded']:
            all_hard.append({**{k: h[k] for k in ('line', 'decl', 'color', 'block')},
                             'file': fr['file']})
        for name, cnt in fr['uses'].items():
            all_uses[name] = all_uses.get(name, 0) + cnt

    variables = []
    for d in all_defs:
        u = all_uses.get(d['name'], 0)
        flag = '未使用' if u == 0 else ('低频' if (min_usage > 0 and u < min_usage) else '')
        variables.append({**d, 'uses': u, 'flag': flag})

    report = {
        'tool': 'extract_css_vars',
        'input': input_path,
        'file_count': len(file_results),
        'files': [os.path.basename(f['file']) for f in file_results],
        'variable_count': len(variables),
        'var_use_total': sum(all_uses.values()),
        'hardcoded_count': len(all_hard),
        'min_usage': min_usage,
        'variables': variables,
        'hardcoded': all_hard,
    }
    if tokens is not None:
        report['token_table'] = check_token_table(all_defs, all_uses, all_hard, tokens)
    return report


def md_table(headers, rows):
    """生成 Markdown 表格文本。"""
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    for r in rows:
        lines.append('| ' + ' | '.join(str(x) for x in r) + ' |')
    return '\n'.join(lines)


def print_report(report):
    """stdout 打印人可读的 Markdown 报告。"""
    print('# CSS 变量提取报告')
    print(f"- 输入：`{report['input']}`（文件数 {report['file_count']}）")
    print(f"- 变量定义：{report['variable_count']} 个；var() 引用总数：{report['var_use_total']}；"
          f"硬编码色值：{report['hardcoded_count']} 处")
    low = report['min_usage']
    print(f"- 低频阈值：--min-usage {low}" + ('（已关闭）' if low <= 0 else ''))

    for cat in ('颜色类', '字号类', '间距/圆角类', '其他类'):
        items = [v for v in report['variables'] if v['category'] == cat]
        print(f"\n## {cat}（{len(items)} 个）")
        if not items:
            print('（无）')
            continue
        rows = [[v['name'], v['value'], v['line'], v['file'], v['uses'], v['flag']] for v in items]
        print(md_table(['变量', '值', '行号', '来源', '引用次数', '标注'], rows))

    print(f"\n## 硬编码色值扫描（未用 var() 包装，共 {report['hardcoded_count']} 处）")
    if report['hardcoded']:
        rows = [[h['line'], h['decl'], h['color'], h['block'] or '—'] for h in report['hardcoded']]
        print(md_table(['行号', '声明', '色值', '所在规则'], rows))
    else:
        print('未发现散落硬编码色值 ✓')

    if 'token_table' in report:
        tt = report['token_table']
        print('\n## Token 表核对')
        print('### 3.1 R4「同语义同色值」')
        if tt['r4']:
            for line in tt['r4']:
                print(f"- {line}")
        else:
            print('未发现异常 ✓')
        print('### 3.2 死 Token（表中定义但源码未使用）')
        if tt['dead']:
            rows = [[d['token'], d['value'], d['note']] for d in tt['dead']]
            print(md_table(['Token', '值', '说明'], rows))
        else:
            print('未发现死 token ✓')
        print('### 3.3 可替换为 var() 的硬编码')
        if tt['replacable']:
            rows = [[r['line'], r['color'], ', '.join(r['suggest'])] for r in tt['replacable']]
            print(md_table(['行号', '硬编码色值', '建议替换'], rows))
        else:
            print('未发现可替换项 ✓')


def main():
    ap = argparse.ArgumentParser(description='CSS 变量批量提取与 Token 表核对工具（设计评估工具链）')
    ap.add_argument('--input', required=True, help='CSS 文件路径或目录（目录递归查找 *.css）')
    ap.add_argument('--token-table', help='Token 表 JSON 文件路径，格式 {"key":"#0e9f8e",...}')
    ap.add_argument('--json', dest='json_out', help='完整结果 JSON 输出路径（stdout 仍打印表格）')
    ap.add_argument('--min-usage', type=int, default=2,
                    help='引用次数低于该值的变量标注"低频"（默认 2；<=0 关闭该标注）')
    args = ap.parse_args()

    # 收集 CSS 文件
    if os.path.isdir(args.input):
        css_files = []
        for root, _dirs, files in os.walk(args.input):
            for fn in sorted(files):
                if fn.lower().endswith('.css'):
                    css_files.append(os.path.join(root, fn))
        css_files.sort()
    else:
        css_files = [args.input]

    if not css_files:
        print(f'[错误] 未在 {args.input} 找到任何 .css 文件', file=sys.stderr)
        sys.exit(1)

    tokens = None
    if args.token_table:
        with open(args.token_table, 'r', encoding='utf-8') as f:
            tokens = json.load(f)
        if not isinstance(tokens, dict):
            print('[错误] --token-table 必须是 {"key":"value",...} 形式的 JSON 对象', file=sys.stderr)
            sys.exit(1)

    file_results = [{**extract_file(p), 'file': p} for p in css_files]
    report = build_report(args.input, file_results, args.min_usage, tokens)
    print_report(report)

    if args.json_out:
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n[已输出] JSON 结果 → {args.json_out}', file=sys.stderr)


if __name__ == '__main__':
    main()
