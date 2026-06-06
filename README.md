# Math-Course-Slides

多门课程的 Beamer 课件, 使用 XeLaTeX 编译。

## 课程目录

| 目录 | 内容 |
|------|------|
| [数学分析](数学分析) | 数学分析 II/III 课件及期中期末复习 slides |
| [实变函数](实变函数) | 实变函数论课件 |
| [高等代数](高等代数) | 奇异值分解、伪逆与最小二乘法 |
| [教学比赛-数学分析](教学比赛-数学分析) | 教学比赛用 slides（级数收敛性、Cesàro 求和等） |
| [数学分析研讨课](数学分析研讨课) | 研讨课课件（解析数论引论等） |
| [大数据分析与数学建模](大数据分析与数学建模) | 线性代数与线性模型基础 |
| [misc](misc) | 通识性内容（优化基础、积分科普） |
| [archive](archive) | 旧版/非正式课件（微积分、线性代数、概率统计、凸优化等） |

## Usage

### 方法一: Overleaf

在 [Overleaf](https://www.overleaf.com/) 中打开本项目, 选择 `XeLaTeX` 编译器, 编译 `main.tex` 即可得到完整 PDF。通过 `main.tex` 中的 `\input{...}` 注释/反注释来切换要编译的内容。

### 方法二: 本地 — 编译单个 section（推荐）

直接使用 [compile.py](compile.py) 的 `--target` / `-t` 参数, 编译指定文件或整个目录:

```bash
# 编译单个 tex 文件（自动生成临时 preamble, 输出到 build/ 下保持目录结构）
python compile.py --target 数学分析/第10章-函数项级数/第4节-函数的幂级数展开

# 编译整个目录下所有 .tex 文件
python compile.py --target 数学分析/第10章-函数项级数

# 简写
python compile.py -t 教学比赛-数学分析/级数的切萨罗求和
```

编译输出位于 `build/` 目录下, 保持与原目录相同的层级结构。如果该节在 `main.tex` 中标记为「未完成」或「待更新」等, 输出文件名会自动添加 `-Incomplete` 后缀。

### 方法三: 本地 — 编译整个 main.tex

```bash
python compile.py                          # 编译 main.tex, 输出到 build/
python compile.py --handout                # 同上 (handout 是默认)
python compile.py --gc                     # 编译后清理辅助文件
python compile.py custom_main.tex          # 用自定义 entry file 编译
```

## 项目结构

```
.
├── main.tex                  # 主入口, 管理所有 \input, 含 preamble
├── compile.py                # 编译脚本
├── common_preamble.tex       # 公共导言区（宏包、定理环境、颜色、字体等）
├── fancy_style_preamble.tex  # 样式导言区（Berkeley 主题、beamer 配色、灰色模式等）
├── plain_preamble.tex        # 极简样式导言区（PlainStyle=true 时启用）
├── colors.tex                # 颜色定义
├── fonts/                    # 中文字体文件
├── images/                   # 图片资源
├── tikz-figures/             # TikZ 图片源文件
├── build/                    # 编译输出
│   ├── main.pdf              # 完整 PDF
│   └── 数学分析/              # --target 编译的节选 PDF
├── 数学分析/
│   ├── 数学分析II-期中复习.tex
│   ├── 数学分析II-期末复习.tex
│   ├── 数学分析II-第二次复习.tex
│   ├── 第7章-定积分/
│   ├── 第8章-反常积分/
│   ├── 第9章-数项级数/
│   ├── 第10章-函数项级数/
│   ├── 第11章-Euclid空间上的极限与连续/
│   └── ...
├── 实变函数/
├── 高等代数/
├── 教学比赛-数学分析/
├── 大数据分析与数学建模/
├── 数学分析研讨课/
├── misc/
└── archive/
```

## 灰色模式

`fancy_style_preamble.tex` 中定义了 `\graymode` / `\normalmode` 命令, 用于将**不做要求的页面**切换为灰色调（包含 sidebar、导航条、标题栏、block 等全部配色）:

```latex
\graymode
\begin{frame}{标题}
  ...
\end{frame}
\normalmode
```

`\graymode` 必须放在 `\begin{frame}` 之前, 因为 Berkeley 主题的 sidebar/headline 在 frame 开始时渲染。`\normalmode` 放在 `\end{frame}` 之后恢复原配色。

## Misc

- [.vscode](.vscode) — VSCode LaTeX Workshop 插件配置文件
- 编译需要 XeLaTeX + latexmk, 以及 `simhei.ttf` 等中文字体（存放于 `fonts/`）
- `common_preamble.tex` 中 `\ifHighContrast` / `\ifShowTocEverySec` / `\ifSiZheng` 等开关可在 `main.tex` 中调整
