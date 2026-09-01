#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
contrast_checker.py —— WCAG 2.x 对比度批量计算与达标判定工具
（设计评估工具链 · 检查工具组）

用途：
  1. 批量计算前景/背景色对的相对亮度与对比度（WCAG 2.x 标准公式：
     sRGB 通道先 /255，再按 0.03928 阈值线性化，L=0.2126R+0.7152G+0.0722B，
     对比度=(L1+0.05)/(L2+0.05)）；
  2. 按上下文判定达标：normal（AA≥4.5 / AAA≥7）、large（AA≥3 / AAA≥4.5）、
     ui 图形/UI 组件（AA≥3，AAA 不适用）；
  3. 支持色值：#hex（3/6 位，兼容 4/8 位）、rgb() / rgba()（alpha 混合到背景并提示）、
     常见 16 具名色；
  4. 输出 Markdown 表格 + 末尾"失守清单"（供门槛扫描直接使用）；--json 输出完整 JSON。

示例命令：
  python3 contrast_checker.py --pairs "#5f6672,#ffffff" --pairs "rgb(14,159,142),#fff"
  python3 contrast_checker.py --file color_pairs.txt
  python3 contrast_checker.py --file color_pairs.json --json out.json --threshold 4.5

参数：
  --pairs     可多次传入，每项 "fg,bg[,context]"
  --file      txt（每行 fg,bg[,context]，# 开头为注释）或 json
              （[{"fg":...,"bg":...,"context":...}, ...]）
  --json      完整结果 JSON 输出路径（stdout 仍打印表格）
  --threshold 自定义 AA 达标线（覆盖各 context 默认 AA 阈值）

仅使用 Python 标准库（re/json/argparse/sys），无第三方依赖。
"""

import argparse
import json
import re
import sys

# 常见 16 具名色（CSS 基础色板）+ orange / grey 别名
NAMED_COLORS = {
    'black': '#000000', 'silver': '#c0c0c0', 'gray': '#808080', 'grey': '#808080',
    'white': '#ffffff', 'maroon': '#800000', 'red': '#ff0000', 'purple': '#800080',
    'fuchsia': '#ff00ff', 'green': '#008000', 'lime': '#00ff00', 'olive': '#808000',
    'yellow': '#ffff00', 'navy': '#000080', 'blue': '#0000ff', 'teal': '#008080',
    'aqua': '#00ffff', 'orange': '#ffa500',
}

# 各 context 的 (AA 阈值, AAA 阈值)；ui 无 AAA（显示 —）
CONTEXT_THRESHOLDS = {
    'normal': (4.5, 7.0),
    'large': (3.0, 4.5),
    'ui': (3.0, None),
}
CONTEXT_ALIASES = {'text': 'normal', 'graphic': 'ui', 'graphics': 'ui', 'component': 'ui'}


def parse_color(s):
    """解析色值为 (r, g, b, alpha)，alpha∈[0,1]。支持 #hex / rgb() / rgba() / 具名色。"""
    s = s.strip().lower()
    if not s:
        raise ValueError('空色值')
    if s in NAMED_COLORS:
        s = NAMED_COLORS[s]
    m = re.fullmatch(r'#([0-9a-f]{6})([0-9a-f]{2})?', s)
    if m:
        r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
        a = int(m.group(2), 16) / 255.0 if m.group(2) else 1.0
        return r, g, b, a
    m = re.fullmatch(r'#([0-9a-f]{3})', s)
    if m:
        h = m.group(1)
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16), 1.0
    m = re.fullmatch(r'#([0-9a-f]{4})', s)  # 4 位 hex（含 alpha）
    if m:
        h = m.group(1)
        return int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16), int(h[3] * 2, 16) / 255.0
    m = re.fullmatch(r'rgba?\(\s*([\d.]+%?)\s*,\s*([\d.]+%?)\s*,\s*([\d.]+%?)\s*'
                     r'(?:,\s*([\d.]+%?)\s*)?\)', s)
    if m:
        def comp(x):
            return round(float(x.rstrip('%')) * 255 / 100) if x.endswith('%') else int(float(x))
        r, g, b = comp(m.group(1)), comp(m.group(2)), comp(m.group(3))
        a = 1.0
        if m.group(4):
            a = float(m.group(4).rstrip('%')) / 100 if m.group(4).endswith('%') else float(m.group(4))
        return r, g, b, a
    raise ValueError(f'无法解析色值: {s}')


def blend(fg, bg):
    """前景带 alpha 时按 alpha 混合到背景（背景按不透明处理），返回 (r,g,b,1.0)。"""
    r = fg[0] * fg[3] + bg[0] * (1 - fg[3])
    g = fg[1] * fg[3] + bg[1] * (1 - fg[3])
    b = fg[2] * fg[3] + bg[2] * (1 - fg[3])
    return round(r), round(g), round(b), 1.0


def channel_linear(v):
    """sRGB 通道线性化（WCAG 2.x，阈值 0.03928）：c/12.92 或 ((c+0.055)/1.055)^2.4。"""
    s = v / 255.0
    if s <= 0.03928:
        return s / 12.92
    return ((s + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    """相对亮度 L = 0.2126R + 0.7152G + 0.0722B。"""
    r, g, b = rgb[0], rgb[1], rgb[2]
    return 0.2126 * channel_linear(r) + 0.7152 * channel_linear(g) + 0.0722 * channel_linear(b)


def contrast_ratio(fg_str, bg_str):
    """计算两个色值字符串的对比度（前景含 alpha 时先混合到背景）。"""
    fg = parse_color(fg_str)
    bg = parse_color(bg_str)
    if fg[3] < 1.0:
        fg = blend(fg, bg)
    l1, l2 = luminance(fg), luminance(bg)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def split_top_level(s):
    """按顶层逗号切分（忽略括号内逗号，兼容 rgb() 内的逗号）。"""
    parts, cur, depth = [], [], 0
    for ch in s:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        if ch == ',' and depth == 0:
            parts.append(''.join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    parts.append(''.join(cur).strip())
    return parts


def normalize_context(c):
    """context 归一化：normal / large / ui；未知值回落 normal。"""
    c = (c or '').strip().lower()
    if c in CONTEXT_ALIASES:
        return CONTEXT_ALIASES[c]
    return c if c in CONTEXT_THRESHOLDS else 'normal'


def parse_context_field(raw, src):
    """解析 context 字段（防"行尾注释污染"坑，KB 图片实测 2026-08-25 实测教训）：
    1) 含 '#' 的行尾注释（如 "ui # 紫条"）自动截断并告警；
    2) 值非法导致静默回落 normal 时告警（合法值 normal/large/ui 或别名 text/graphic/component）。"""
    if raw is None:
        return 'normal'
    s = str(raw)
    if '#' in s:
        s2 = s.split('#', 1)[0].strip()
        print(f'[警告] {src} context 字段含 # 行尾注释，已截断: "{s}" -> "{s2}"（txt 注释请整行以 // 开头）',
              file=sys.stderr)
        s = s2
    ctx = normalize_context(s)
    if ctx == 'normal' and s.strip().lower() not in ('', 'normal', 'text'):
        print(f'[警告] {src} context 值无法识别: "{s}"，已按 normal 处理。'
              f'合法值: normal / large / ui（别名 text / graphic / component）', file=sys.stderr)
    return ctx


def load_pairs(args):
    """汇总 --pairs 与 --file 的色对 → [(fg, bg, context)]。"""
    pairs = []
    for p in args.pairs or []:
        parts = split_top_level(p)
        if len(parts) < 2:
            print(f'[警告] 跳过无法解析的 --pairs: {p}', file=sys.stderr)
            continue
        ctx = parse_context_field(parts[2], f'--pairs "{p}"') if len(parts) > 2 else 'normal'
        pairs.append((parts[0], parts[1], ctx))
    if args.file:
        path = args.file
        if path.lower().endswith('.json'):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise SystemExit('[错误] --file json 必须是数组')
            for i, item in enumerate(data):
                fg = item.get('fg') or item.get('foreground')
                bg = item.get('bg') or item.get('background')
                if not fg or not bg:
                    print(f'[警告] 跳过第 {i + 1} 项（缺 fg/bg）: {item}', file=sys.stderr)
                    continue
                pairs.append((str(fg), str(bg), parse_context_field(item.get('context', 'normal'), f'{path} 第 {i + 1} 项')))
        else:
            with open(path, 'r', encoding='utf-8') as f:
                for ln, line in enumerate(f, 1):
                    line = line.strip()
                    # 注意：不能以 '#' 判注释（hex 色值也以 # 开头），改用 '//'
                    if not line or line.startswith('//'):
                        continue
                    parts = split_top_level(line)
                    if len(parts) < 2:
                        print(f'[警告] {path}:{ln} 跳过（需要 fg,bg）: {line}', file=sys.stderr)
                        continue
                    ctx = parse_context_field(parts[2], f'{path}:{ln}') if len(parts) > 2 else 'normal'
                    pairs.append((parts[0], parts[1], ctx))
    if not pairs:
        raise SystemExit('[错误] 未提供任何色对（--pairs 或 --file 至少其一）')
    return pairs


def evaluate(pairs, threshold_override):
    """逐对计算对比度与达标判定 → (results, errors)。"""
    results, errors = [], []
    for i, (fg_s, bg_s, ctx) in enumerate(pairs, 1):
        aa_t, aaa_t = CONTEXT_THRESHOLDS[ctx]
        if threshold_override is not None:
            aa_t = threshold_override
        try:
            fg = parse_color(fg_s)
            bg = parse_color(bg_s)
            alpha_warn = fg[3] < 1.0
            eff_fg = blend(fg, bg) if alpha_warn else fg
            c = contrast_ratio(fg_s, bg_s)
            aa = c >= aa_t
            aaa = (c >= aaa_t) if aaa_t is not None else None
            results.append({
                'index': i, 'fg': fg_s, 'bg': bg_s, 'context': ctx,
                'contrast': round(c, 4), 'aa': aa, 'aaa': aaa, 'pass': aa,
                'threshold_aa': aa_t, 'threshold_aaa': aaa_t,
                'alpha_warning': alpha_warn,
                'blended_fg': f'#{eff_fg[0]:02x}{eff_fg[1]:02x}{eff_fg[2]:02x}' if alpha_warn else None,
            })
        except ValueError as e:
            errors.append({'index': i, 'fg': fg_s, 'bg': bg_s, 'context': ctx, 'error': str(e)})
    return results, errors


def md_table(headers, rows):
    """生成 Markdown 表格文本。"""
    lines = ['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |']
    for r in rows:
        lines.append('| ' + ' | '.join(str(x) for x in r) + ' |')
    return '\n'.join(lines)


def print_results(results, errors, source_desc, threshold_override):
    """stdout 打印表格与失守清单。"""
    print('# 对比度批量计算报告（WCAG 2.x）')
    print(f'- 输入：{source_desc}；色对 {len(results)} 组'
          + (f'；解析失败 {len(errors)} 组' if errors else ''))
    if threshold_override is not None:
        print(f'- 自定义 AA 达标线：{threshold_override}')
    print()

    if results:
        headers = ['序号', '前景', '背景', '对比度', 'AA', 'AAA', '判定']
        rows = []
        for r in results:
            aa = f"通过 (≥{r['threshold_aa']:g})" if r['aa'] else f"未过 (≥{r['threshold_aa']:g})"
            if r['aaa'] is None:
                aaa = '—'
            else:
                aaa = f"通过 (≥{r['threshold_aaa']:g})" if r['aaa'] else f"未过 (≥{r['threshold_aaa']:g})"
            verdict = '达标' if r['pass'] else '失守'
            rows.append([r['index'], r['fg'], r['bg'], f"{r['contrast']:.2f}:1", aa, aaa,
                         f"{verdict} ({r['context']})"])
        print(md_table(headers, rows))

    if errors:
        print('\n## 解析失败项')
        for e in errors:
            print(f"- 序号 {e['index']}：{e['fg']} / {e['bg']} → {e['error']}")

    failed = [r for r in results if not r['pass']]
    print(f"\n## 失守清单（{len(failed)} 项）—— 供门槛扫描直接使用")
    if failed:
        rows = [[r['index'], r['fg'], r['bg'], f"{r['contrast']:.2f}:1",
                 f"≥{r['threshold_aa']:g}", r['context']] for r in failed]
        print(md_table(['序号', '前景', '背景', '对比度', 'AA 要求', 'context'], rows))
    else:
        print('全部达标 ✓')


def main():
    ap = argparse.ArgumentParser(description='WCAG 2.x 对比度批量计算与达标判定工具（设计评估工具链）')
    ap.add_argument('--pairs', action='append', help='色对 "fg,bg[,context]"，可多次传入')
    ap.add_argument('--file', help='txt（每行 fg,bg[,context]）或 json 文件')
    ap.add_argument('--json', dest='json_out', help='完整结果 JSON 输出路径（stdout 仍打印表格）')
    ap.add_argument('--threshold', type=float, help='自定义 AA 达标线（覆盖各 context 默认值）')
    ap.add_argument('--fail-on-issues', action='store_true',
                    help='CI 门禁模式：存在失守色对时退出码为 1（全部达标退出码 0）')
    args = ap.parse_args()
    if not args.pairs and not args.file:
        ap.error('至少提供 --pairs 或 --file 之一')

    pairs = load_pairs(args)
    results, errors = evaluate(pairs, args.threshold)

    if args.file:
        src = args.file
        if args.pairs:
            src += '（另加 --pairs 若干组）'
    else:
        shown = ', '.join(args.pairs[:3]) + (' …' if len(args.pairs) > 3 else '')
        src = '--pairs ' + shown

    print_results(results, errors, src, args.threshold)

    if args.json_out:
        out = {
            'tool': 'contrast_checker',
            'source': src,
            'threshold_override': args.threshold,
            'pairs': results,
            'errors': errors,
            'summary': {
                'total': len(results),
                'passed': sum(1 for r in results if r['pass']),
                'failed': sum(1 for r in results if not r['pass']),
                'max_contrast': max((r['contrast'] for r in results), default=None),
                'min_contrast': min((r['contrast'] for r in results), default=None),
            },
            'failed': [r for r in results if not r['pass']],
        }
        with open(args.json_out, 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f'[已输出] JSON 结果 → {args.json_out}', file=sys.stderr)

    if args.fail_on_issues and any(not r['pass'] for r in results):
        n_fail = sum(1 for r in results if not r['pass'])
        print(f'[CI 门禁] {n_fail} 条色对失守，退出码 1', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
