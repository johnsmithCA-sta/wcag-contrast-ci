# CI Gate · 对比度与 CSS Token 卫生自动化门禁
# CI Gate for Contrast & CSS Token Hygiene

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) ![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg) ![Release](https://img.shields.io/badge/Release-v0.1.1-green.svg) ![SkillHub](https://img.shields.io/badge/SkillHub-@user_65c8c185%2Fwcag-contrast-ci-orange.svg)

**English** — A CI gate for WCAG contrast and CSS token hygiene. Fails the build on contrast regressions and design-token drift. Pure Python standard library, zero third-party dependencies.

Catches the failures that code review misses and that reach production: **a colour pair that dropped below AA, a token that silently changed, a hardcoded hex that bypassed the system**.

**Install / 安装**

```bash
skillhub install wcag-contrast-ci --namespace user_65c8c185
# or / 或
git clone https://github.com/johnsmithCA-sta/wcag-contrast-ci.git
```

---

> **零第三方依赖（仅 Python 标准库）· 可独立分发作 CI 门禁 · 五分钟接入 GitHub Actions**
> **Zero third-party dependencies (Python standard library only) · Ship as a standalone CI gate · Five-minute integration with GitHub Actions**

---

## 它能做什么 / What it does

**两个独立的 Python 标准库脚本**，直接 `cp` 到 CI 流水线即可跑：

**Two independent Python-standard-library scripts. Copy them straight into your CI pipeline.**

### `contrast_checker.py` — 对比度门禁 / Contrast Gate

批量校验前景 / 背景色对的 WCAG 2.x 对比度，支持 normal / large / ui 三种达标线，默认 AA 级。失守即退出码 1，CI 步骤失败。

Batch-validates WCAG 2.x contrast ratios for foreground/background color pairs. Supports `normal` / `large` / `ui` thresholds (WCAG AA defaults). Exit code 1 on failure — CI step fails.

```bash
cat > color-pairs.txt <<'EOF'
#ffffff,#1a2c44,normal
#64748d,#ffffff,normal
#ffffff,#533afd,ui
EOF

python3 contrast_checker.py --file color-pairs.txt --fail-on-issues
```

### `extract_css_vars.py` — CSS Token 卫生门禁 / CSS Token Hygiene Gate

递归扫描 `*.css`，提取 `var()` 定义与引用、硬编码色值、无人使用的死 Token。支持自定义 Token 表核对（同语义双色值 / 可替换硬编码）。输出 Markdown 表 + 完整 JSON。

Recursively scans `*.css` files for `var()` definitions, usages, hard-coded color values, and dead tokens. Supports a token-table check (semantic duplicates / replaceable hard-codes). Emits a Markdown table on stdout and a full JSON report.

```bash
python3 extract_css_vars.py --input dist/css/ --json token-report.json

# 带 Token 表核对 / With token-table cross-check
python3 extract_css_vars.py --input dist/css/ --token-table tokens.json \
  --json token-report.json --min-usage 3
```

---

## 为什么 CI 自动跑还不够：合规过了 ≠ 设计好 / Why CI automation alone isn't enough

对比度失守只是 8 个维度里**最容易量化的一环**。

视觉层级混乱、触控目标过小、Token 体系失控、信息密度失衡、文案扫读障碍、状态可识别性差……这些更难察觉的问题，才是真正拉低转化与体验的元凶——

**合规过了 ≠ 设计好。** 自动化只能守住下限，剩下 7 个维度需要体系化的设计评估方法去发现和归因。

We flag contrast failures because they are **the easiest of 8 dimensions to quantify**.

But the real culprits behind conversion and UX regressions are far quieter: visual hierarchy collapse, undersized touch targets, an unstable token system, mismatched information density, broken scannability, indistinguishable states.

**Compliance passed ≠ good design.** Automation only enforces the floor. The remaining seven dimensions require a systematic evaluation methodology to surface and attribute.

> 完整设计评估体系（八维评分 · 锚定量表 · 失分模式库 · 案例归因 SOP）正在内测，
> 商业版面向团队授权与持续校准更新订阅。免费版守住下限，商业版托起上限。
>
> *A full design evaluation methodology (8-dimension scoring · anchoring scale · failure-pattern library · case-attribution SOP) is in private beta. The commercial release ships as a team license plus calibration-update subscription. Free version guards the floor; the commercial release raises the ceiling.*

---

## 示例评估演示 / A Demo of the Methodology in Action

下面是同一份截图与「眯眼测试」前后对比——左侧是常规视图，右侧是色块网格化后的视觉重量分布。眯眼（模糊）后第一焦点在哪里、应该在哪里，是判断「视觉层级是否错位」的快速工具。

Below: a side-by-side of a regular screenshot versus its color-block grid (the "squint test"). Where does the dominant mass land after blurring — and where should it land? A fast read on whether the visual hierarchy is misaligned.

![blur_grid 对比演示](./docs/blur_grid_compare.png)

| 区域 / Region | 原图直觉 / In the original | 眯眼后 / After blur |
|---|---|---|
| 主标题区 / Headline | 字号偏小、层级弱 | 几乎「空」 |
| KPI 卡群 / KPI cards | 标签浅、数值大 | **视觉重量最重的色块** |
| 主按钮 / Primary CTA | 白字浅底，对比度不足 | 模糊后仅剩一团淡色 |

> 评估时眯眼看一眼：焦点是落在页面想要用户行动的位置上吗？——对比度门禁不会告诉你答案。
>
> *Squint at it: does the focus land where the page wants users to act? A contrast gate won't tell you.*

> 完整示例报告（B 端看板实跑 + 两个行业虚构样张）与体检卡样张见 [`examples/`](./examples/)。免费脚本输出为机器可读的对比度 / Token 检查结果；示例报告展示的是商业版完整评估的输出形态。
>
> *Full sample reports (a real-run B2B dashboard plus two fictional industry samples) and the health-card sample live in [`examples/`](./examples/). The free scripts emit machine-readable contrast/token checks; the sample reports demonstrate the commercial version's full evaluation output.*

---

## 商业版内测预约 / Commercial Beta Waitlist

商业版内测中。如希望团队优先体验完整体系（八维评分 · 锚定量表 · 失分模式库 · 持续校准更新），可加入意向名单：

*The commercial release is in private beta. If you'd like your team to trial the full methodology (8-dimension scoring · anchoring scale · failure-pattern library · continuous calibration updates), join the waitlist:*

- 📬 **邮件预约（推荐）** / *Email (preferred)*：`epcz6124@agent.qq.com`，主题含 `[commercial-beta]`，一两句话说明团队规模与想解决的设计问题即可 / *Subject line `[commercial-beta]`; a sentence on team size and the design problem you want solved is enough.*
- 💬 **GitHub Issue 留言** / *Or open an [issue](../../issues)*：标题同样含 `[commercial-beta]` / *Title it `[commercial-beta]` too.* 介意公开联系方式请改用邮件 / *If you'd rather not post contact details publicly, email instead.*

---

## GitHub Actions 接入 / GitHub Actions Integration

```yaml
name: a11y-contrast-gate
on: [pull_request]
jobs:
  contrast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          mkdir -p ci-tools
          curl -sSL https://raw.githubusercontent.com/johnsmithCA-sta/wcag-contrast-ci/main/contrast_checker.py -o ci-tools/contrast_checker.py
          curl -sSL https://raw.githubusercontent.com/johnsmithCA-sta/wcag-contrast-ci/main/extract_css_vars.py -o ci-tools/extract_css_vars.py
          python3 ci-tools/contrast_checker.py --file .a11y/color-pairs.txt --fail-on-issues
          python3 ci-tools/extract_css_vars.py --input dist/css/ --json token-report.json
```

---

## 退出码约定 / Exit Code Convention

| 工具 / Tool | 场景 / Scenario | 退出码 / Exit |
|---|---|---|
| `contrast_checker` | 全部达标 / All pass | `0` |
| `contrast_checker` | 有失守且未指定 `--fail-on-issues` / Failures without `--fail-on-issues` | `0` |
| `contrast_checker` | `--fail-on-issues` 且存在失守色对 / Failures with `--fail-on-issues` | `1` |
| `contrast_checker` | 参数/输入错误 / Argument or input error | `2` |
| `extract_css_vars` | 正常完成 / Completed (parse JSON for hard-coded/dead-token signals) | `0` |
| `extract_css_vars` | 参数/输入错误 / Argument or input error | `2` |

---

## 信任背书 / Trust Signal

- ✅ **通过 10 组回归测试**（公开标准用例，含已知失守色对、Token 卫生正向/反向用例）
- ✅ **零第三方依赖**：纯 Python 标准库，无 `pip install`，适合锁定运行时环境
- ✅ **MIT 协议**，可自由 fork、改用、商用，无需署名（仅保留版权声明即可）

*Passes 10 regression test groups (public standard fixtures: known-failing color pairs, token-hygiene positive/negative cases).*
*Zero third-party dependencies — pure Python standard library, no `pip install`, safe for locked environments.*
*MIT licensed — fork, modify, ship commercially without attribution (copyright notice preserved as-is is sufficient).*

---

## 法律免责声明 / Legal Disclaimer

本仓库脚本是**设计质量门禁工具**，不是法律合规认证。
WCAG / ADA / EN 301 549 等正式无障碍审计须由持证机构出具。

*This repository is a **design-quality gating tool**, not a legal-compliance certification.*
*Formal WCAG / ADA / EN 301 549 accessibility audits must be issued by accredited bodies.*

---

## 协议 / License

[MIT](./LICENSE) · Copyright © 2026 johnsmithCA-sta
商业版另议授权条款 / Commercial version uses a separate license — see the waitlist note above.

---

<sub>From the **完整设计评估体系**（commercial beta — see waitlist above）by johnsmithCA-sta · v0.1.1 · 2026-09-01</sub>