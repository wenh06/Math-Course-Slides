# 数学分析编程习题 — 评分环境说明

本目录基于 [nbgrader](https://nbgrader.readthedocs.io/) 管理和批改编程作业。
为隔离学生代码的任意执行，所有自动批改均在 Docker 容器内完成。

---

## 目录结构

```
数学分析-编程习题/
├── Dockerfile               # 评分沙箱镜像定义
├── nbgrader_config.py       # nbgrader 配置
├── gradebook.db             # 成绩数据库（自动生成）
├── c-solutions/             # C 语言参考答案（教师自留，勿发给学生）
│   └── 第7章-定积分/
│       └── 第6节-定积分的数值计算/
│           ├── integration.h
│           └── solution.c
├── source/                  # 教师版（含答案和 hidden tests）
│   ├── header.ipynb         # 作业头（填姓名/学号提示，每份作业自动插入）
│   └── 第7章-定积分/
│       ├── integration.h             # C 版：学生须遵循的函数签名
│       ├── solution.c                # C 版：发给学生的代码框架（stub）
│       ├── 第6节-定积分的数值计算.ipynb      # Python 版
│       └── 第6节-定积分的数值计算-c.ipynb   # C 版（同一 assignment，平行 notebook）
├── release/                 # 学生版（由 generate_assignment 生成，勿手动修改）
│   └── 第7章-定积分/
│       ├── integration.h
│       ├── solution.c
│       ├── 第6节-定积分的数值计算.ipynb
│       └── 第6节-定积分的数值计算-c.ipynb
└── submitted/               # 学生提交（按学号手动整理，见第三节）
    └── <学号>/
        └── 第7章-定积分/
            ├── 第6节-定积分的数值计算.ipynb   # Python 版：只提交此 notebook
            ├── 第6节-定积分的数值计算-c.ipynb  # C 版：提交此 notebook（无需修改）
            └── solution.c                      # C 版：学生实现
```

> **`integration.h` 和 `solution.c`（stub）与 notebook 同放在
> `source/第7章-定积分/` 下，`generate_assignment` 会将该目录下的所有文件
> 一并复制到 `release/`，学生下载 release 即可得到完整材料，无需额外分发。**

---

## 一、构建 Docker 镜像

```bash
# 在本目录下执行
docker build -t nbgrader-math .
```

镜像基于 `python:3.12-slim`，仅包含：
- `numpy` / `sympy` / `mpmath`（作业所需包）
- `nbgrader`（自动批改，依赖 `nbconvert` 等）
- `gcc` / `make`（仅 C 语言作业需要，纯 Python 可从 Dockerfile 删去）

### 1.1 网络受限时（代理 / Docker Hub 不稳定）

如果构建时报 `DeadlineExceeded` / `i/o timeout`，通常是 Docker Hub 在国内访问不稳定。可通过代理构建：

```bash
docker build --network host \
  --build-arg HTTP_PROXY=http://<PROXY_HOST>:<PROXY_PORT> \
  --build-arg HTTPS_PROXY=http://<PROXY_HOST>:<PROXY_PORT> \
  -t nbgrader-math .
```

- `<PROXY_HOST>:<PROXY_PORT>` 替换为本机代理地址。
- `--network host` 确保构建阶段 `RUN` 指令也走宿主机网络从而可达代理。
- 若 `FROM` 拉取基础镜像仍超时，可在 `/etc/docker/daemon.json` 中配置：
  ```json
  { "proxies": { "http-proxy": "http://<PROXY_HOST>:<PROXY_PORT>", "https-proxy": "http://<PROXY_HOST>:<PROXY_PORT>" } }
  ```
  然后 `sudo systemctl restart docker` 后再 build。

> `--build-arg` 的值仅作用于构建阶段，不会固化到镜像中。

---

## 二、生成学生版作业（generate_assignment）

> 此步骤会剥除 `### BEGIN SOLUTION ... ### END SOLUTION` 之间的答案，
> 并将 hidden tests 替换为空 cell，生成 `release/` 目录。

```bash
docker run --rm \
  -v "$(pwd)":/course \
  nbgrader-math \
  nbgrader generate_assignment 第7章-定积分 --force
```

将 `release/第7章-定积分/` 整个目录发给学生即可。

---

## 三、提交结构与收集（autograde）

### 3.1 提交结构约定

nbgrader 通过 `submitted/<学号>/` 这个**目录名**来识别学生身份，与 notebook
内填写的 `NAME` / `STUDENT_ID` 字段无关（后者仅供人工核查）。

因此收到学生提交后，需要按**学号**重命名并组织到以下结构：

```
submitted/
└── 2024001/              ← 目录名 = 学号
    └── 第7章-定积分/
        └── 第6节-定积分的数值计算.ipynb    # Python 版
```

C 版提交（notebook 本身无需修改，只需附上 `solution.c`）：

```
submitted/
└── 2024001/
    └── 第7章-定积分/
        ├── 第6节-定积分的数值计算-c.ipynb   ← 与 release/ 中相同，不用改
        └── solution.c                        ← 学生写的 C 实现
```

`nbgrader autograde` 会把 `submitted/<学号>/<作业>/` 整个目录（含 `solution.c`）
复制到 `autograded/<学号>/<作业>/` 后再执行 notebook，因此 `solution.c` 会在执行
时自动可见。

```bash
docker run --rm \
  -v "$(pwd)":/course \
  nbgrader-math \
  nbgrader autograde 第7章-定积分
```

- 执行结果写入 `autograded/<学号>/第7章-定积分/`
- 成绩写入 `gradebook.db`

> **安全说明**：学生 notebook 在容器内执行，宿主机文件系统权限受限于
> 挂载路径，网络默认不隔离。如需更严格的沙箱，可在 `docker run` 中
> 加 `--network none --read-only`（需同时将 `/course` 设为可写卷）。

### 3.3 生成反馈（可选）

```bash
docker run --rm \
  -v "$(pwd)":/course \
  nbgrader-math \
  nbgrader generate_feedback 第7章-定积分
```

反馈 HTML 文件生成于 `feedback/<学号>/第7章-定积分/`。

### 3.4 导出成绩

```bash
docker run --rm \
  -v "$(pwd)":/course \
  nbgrader-math \
  nbgrader export
```

或直接查询 SQLite 数据库：

```bash
sqlite3 gradebook.db \
  "SELECT student_id, score, max_score FROM grade JOIN submission USING(submission_id) JOIN assignment USING(assignment_id) WHERE assignment.name='第7章-定积分';"
```

---

## 四、C 语言提交方案

### 4.1 核心思路：grading cell 与语言无关

nbgrader 的 grading cell 只是普通 Python 断言，例如：

```python
assert np.allclose(composite_trapezoid(p3_f2, 0, np.pi, 8), p3_true_val_2, atol=1e-2)
```

它不在乎 `composite_trapezoid` 是学生写的 Python 函数，还是从 C 编译出来再用
`ctypes` 包装的函数——只要 **Python 命名空间里存在这个名字、签名一致**，断言就能运行。

因此，C 版作业 notebook 的结构与 Python 版几乎完全一致：

| notebook 区域 | Python 版 | C 版 |
|---|---|---|
| solution cell | 学生在此写 Python 函数 | **换成 locked setup cell**，编译 `solution.c` 并暴露同名 Python 包装 |
| grading cell | `assert np.allclose(composite_trapezoid(...), ...)` | **完全相同，一字不改** |

所以 grading cell 可以直接从 Python 版 source notebook 复制，不需要为 C 单独维护。

### 4.2 提交约定

学生选择 C 版时**只需提交一个额外文件**：`solution.c`（在 notebook 旁边）。
不需要 Makefile，不需要 `main()`，编译由评分环境统一处理。

发给学生的材料（`release/第7章-定积分/` 目录下，`generate_assignment` 自动生成）：

| 文件 | 说明 |
|---|---|
| `integration.h` | 函数签名约定，**不可修改** |
| `solution.c` | 代码框架（stub），学生在此基础上实现后一并提交 |
| `第6节-定积分的数值计算-c.ipynb` | C 版 notebook，**不需要修改**，直接提交即可 |

### 4.3 C 函数签名

`source/第7章-定积分/integration.h`：

```c
typedef double (*func_t)(double x);

double composite_trapezoid(func_t f, double a, double b, int m);
double composite_simpson  (func_t f, double a, double b, int m);
double romberg            (func_t f, double a, double b, double tol);
double gauss_legendre     (func_t f, double a, double b, int n);
```

`func_t` 是被积函数的函数指针，Python 端用 `ctypes.CFUNCTYPE` 传入。

### 4.4 C 版 source notebook 与 Python 版平行存放

**Python 版 source notebook 不需要任何修改。**

C 版与 Python 版在同一个 assignment 文件夹下平行存放，`integration.h` 和
`solution.c`（stub）也放在这里，`generate_assignment` 一次性将所有文件复制到 `release/`：

```
source/第7章-定积分/
├── integration.h                          ← C 版配套，随 release 一同下发
├── solution.c                             ← C 版配套（stub），随 release 一同下发
├── 第6节-定积分的数值计算.ipynb           ← Python 版（保持不动）
└── 第6节-定积分的数值计算-c.ipynb        ← C 版（已创建）
```

---

## 五、版本固定（推荐）

为保证长期可复现，建议在 Dockerfile 中固定包版本：

```dockerfile
RUN pip install --no-cache-dir \
    numpy==1.26.4 \
    sympy==1.12 \
    mpmath==1.3.0 \
    nbgrader==0.9.3
```

可通过以下命令查询当前容器内的版本：

```bash
docker run --rm nbgrader-math pip freeze | grep -E 'numpy|sympy|mpmath|nbgrader'
```
