# CI 门禁包（contrast_checker + extract_css_vars）

> 零第三方依赖（仅 Python 标准库），可独立分发作 CI 门禁，用于 Web 项目的无障碍对比度与 Token 卫生自动化检查。

## 提取独立运行

两个脚本位于技能包 `scripts/`，不依赖技能包其他文件，直接复制即可独立使用：

```bash
mkdir -p ci-tools && cd ci-tools
cp /path/to/ui-design-eval/scripts/contrast_checker.py .
cp /path/to/ui-design-eval/scripts/extract_css_vars.py .
```

## contrast_checker.py —— 对比度门禁

```bash
# 1) 色对清单文件（每行 fg,bg[,context]，# 开头为注释；context: normal|large|ui）
cat > color-pairs.txt <<'EOF'
#ffffff,#1a2c44,normal
#64748d,#ffffff,normal
#ffffff,#533afd,ui
EOF

# 2) 门禁运行：失守即退出码 1（CI 步骤失败），全部达标退出码 0
python3 contrast_checker.py --file color-pairs.txt --fail-on-issues

# 3) 输出完整 JSON 供下游步骤解析
python3 contrast_checker.py --file color-pairs.txt --json result.json --fail-on-issues
```

- 默认达标线：normal ≥4.5（WCAG AA 正文）、large ≥3（大字）、ui ≥3（图形对象）；`--threshold` 可覆盖
- `--pairs "#fff,#000,normal"` 可多次传入，适合单条快速检查
- JSON 结构含 `summary.passed/failed`、`failed[]`（失守详情含色值/对比度/context/达标线）

## extract_css_vars.py —— Token 卫生门禁

```bash
# 扫描 CSS 目录：提取 var() 定义/引用、硬编码色值、死 Token
python3 extract_css_vars.py --input dist/css/ --json token-report.json

# 带 Token 表核对（同语义双色值/硬编码/可替换）
python3 extract_css_vars.py --input dist/css/ --token-table tokens.json --json token-report.json --min-usage 3
```

- `--input` 支持单文件或目录（递归 `*.css`）；`--min-usage` 控制死 Token 判定阈值
- 输出 Markdown 表（stdout）+ 完整 JSON（--json）

## GitHub Actions 示例

```yaml
name: a11y-contrast-gate
on: [pull_request]
jobs:
  contrast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          cp ci-tools/contrast_checker.py .
          python3 contrast_checker.py --file .a11y/color-pairs.txt --fail-on-issues
```

## 退出码约定

| 工具 | 场景 | 退出码 |
|---|---|---|
| contrast_checker | 全部达标 / 有失守且未指定 `--fail-on-issues` | 0 |
| contrast_checker | `--fail-on-issues` 且存在失守色对 | 1 |
| contrast_checker | 参数/输入错误 | 2 |
| extract_css_vars | 正常完成（含发现硬编码/死 Token，需自行解析 JSON 判定） | 0 |
| extract_css_vars | 参数/输入错误 | 2 |

> 注：本包为设计质量门禁，非法律合规认证（WCAG/ADA 正式审计须由持证机构出具）。
