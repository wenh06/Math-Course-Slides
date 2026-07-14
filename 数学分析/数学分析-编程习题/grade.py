#!/usr/bin/env python3
"""grade.py — 批改 submitted/ 下所有 zip 提交

用法：
  python3 grade.py                # 解压新提交并批改（已有成绩的学号自动跳过）
  python3 grade.py --grade-only   # 仅批改，不解压
  python3 grade.py --overwrite    # 全部重新批改（忽略已有成绩）
"""

import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ASSIGNMENT = "第7章-定积分"
SUBMITTED_DIR = Path("submitted")
EXTRACT_SUBDIR = "第7章-定积分"
DB_PATH = "gradebook.db"


def get_graded_students() -> set[str]:
    """从数据库取已有本作业成绩的学号"""
    if not Path(DB_PATH).exists():
        return set()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT st.id
            FROM grade g
            JOIN submitted_notebook sn ON g.notebook_id = sn.id
            JOIN submitted_assignment sa ON sn.assignment_id = sa.id
            JOIN student st ON sa.student_id = st.id
            JOIN assignment a ON sa.assignment_id = a.id
            WHERE a.name = ? AND g.auto_score IS NOT NULL;
            """,
            (ASSIGNMENT,),
        )
        return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()
    finally:
        con.close()


def collect_submission_files(
    root: Path,
) -> tuple[list[Path], list[Path]]:
    """从提取目录中收集所有提交文件 (.ipynb, .c, .h)。

    遍历所有非垃圾目录。不按单个目录筛选——因为：
    - Windows 解压可能把不同编码的目录项合并
    - zip 可能内含多个作业目录
    - 学生可能多次压缩导致目录结构混乱

    返回 (notebook_files, aux_files)。
    """

    def is_junk(path: Path) -> bool:
        if "__MACOSX" in path.parts or ".ipynb_checkpoints" in path.parts:
            return True
        # Jupyter 自动保存的 -checkpoint 文件（如 "xxx-checkpoint.ipynb"）不是学生提交
        stem = path.stem
        if stem.endswith("-checkpoint") or stem.endswith("-nbautoexport"):
            return True
        return False

    notebooks: list[Path] = []
    aux: list[Path] = []
    seen: set[Path] = set()
    for f in root.rglob("*"):
        if not f.is_file() or is_junk(f) or f in seen:
            continue
        seen.add(f)
        if f.suffix == ".ipynb":
            notebooks.append(f)
        elif f.suffix in (".c", ".h"):
            aux.append(f)
    return notebooks, aux


def compute_zip_hash(zip_path: Path) -> str:
    """计算 zip 文件内容的 hash（SHA256）"""
    import hashlib

    h = hashlib.sha256()
    with zip_path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_zip_hashes() -> dict[str, str]:
    """加载已记录的 zip hash（路径: hash）"""
    hash_file = SUBMITTED_DIR / ".zip_hashes.json"
    if hash_file.exists():
        import json

        return json.loads(hash_file.read_text())
    return {}


def save_zip_hashes(hashes: dict[str, str]) -> None:
    """保存 zip hash 记录"""
    import json

    hash_file = SUBMITTED_DIR / ".zip_hashes.json"
    hash_file.write_text(json.dumps(hashes, indent=2, ensure_ascii=False))


def expected_notebook_names() -> list[str]:
    """从 release 目录获取预期的 notebook 文件名"""
    release_dir = Path("release") / EXTRACT_SUBDIR
    if release_dir.exists():
        return [f.name for f in release_dir.glob("*.ipynb")]
    return []


def is_unexpected_name(name: str, expected: list[str]) -> bool:
    """判断文件名是否含有不期望的前缀/后缀"""
    stem = Path(name).stem
    # strip common whitespace variants
    stem = stem.rstrip(" \t　_-")
    return stem not in expected


def fuzzy_rename(name: str, expected: list[str]) -> str:
    """把改名后的 notebook 名纠正回标准名。返回纠正后的文件名，匹配不到则返回原名。

    按 expected 列表顺序（-c 在前，普通在后）依次做前缀匹配：
    - 某 expected 的 stem 是 name 的前缀，且 name 比它长 → 命中，返回该 expected
    - 这样 "xxx-c最终版" 会被 -c 优先命中，不会错误地退化为普通版
    - 都不匹配 → 返回原名
    """
    stem = Path(name).stem
    for e in expected:
        e_stem = Path(e).stem
        if stem == e_stem:
            return name  # 已是标准名
        if stem.startswith(e_stem):
            return e
    return name


def rename_unexpected_notebooks(notebooks: list[Path]) -> list[tuple[Path, str]]:
    """检测改名文件，返回 (原文件, 纠正后文件名) 列表。不在此函数内重命名磁盘文件。"""
    expected = expected_notebook_names()
    if not expected:
        return []
    # 按 stem 长度降序：更具体的（如 -c 版本）优先匹配，避免被短前缀截胡
    expected_sorted = sorted(expected, key=lambda e: len(Path(e).stem), reverse=True)
    renames: list[tuple[Path, str]] = []
    for nb in notebooks:
        new_name = fuzzy_rename(nb.name, expected_sorted)
        if new_name != nb.name:
            renames.append((nb, new_name))
    return renames


def _try_decode_gbk(name: str) -> str | None:
    """尝试把 cp437 box-drawing 乱码文件名还原为 GBK 中文。
    安全过滤：cp437 无法编码（含几乎所有非拉丁字符）或 GBK 解码失败时返回 None。
    """
    try:
        raw = name.encode("cp437", errors="strict")
        decoded = raw.decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError, ValueError):
        return None
    return decoded if decoded != name else None


def _fix_gbk_filenames(root: Path, expected_names: list[str]) -> None:
    """Windows 中文系统打包的 zip 常以 GBK 编码存储文件名，Python 默认按 UTF-8 解压
    会生成乱码文件名（如 "╡┌6╜┌-╢¿╗².ipynb"）。仅当 GBK 解码后的名字命中某个预期文件名
    时才重原名 —— 避免误改无法确认是 GBK 乱码的文件名（如含特殊数学符号等）。
    """
    expected_set = set(expected_names)
    # 自深至浅重命名，避免目录先改名导致子路径失效
    for p in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if p.name in expected_set:
            continue  # 已经是标准名，不动
        decoded = _try_decode_gbk(p.name)
        if decoded and decoded in expected_set:
            p.rename(p.parent / decoded)


def extract_submission(zip_path: Path, target: Path) -> tuple[bool, str, str]:
    """解压单个学生提交到 target。返回 (是否成功, 失败原因)"""
    target.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path)
        except zipfile.BadZipFile:
            return False, "zip 文件损坏", []

        # 修复 GBK 编码文件名（Windows 中文系统打包常见）
        _fix_gbk_filenames(tmp_path, expected_notebook_names())

        notebooks, aux = collect_submission_files(tmp_path)
        if not notebooks:
            names = [info.filename for info in zipfile.ZipFile(zip_path, "r").infolist() if not info.is_dir()]
            return False, f"未找到 .ipynb 文件，zip 内容：{names[:10]}", []

        # 检测并纠正改名的 notebook
        renames = rename_unexpected_notebooks(notebooks)
        rename_map = {nb.name: new_name for nb, new_name in renames}

        # 把收集到的文件复制到目标目录
        # 同名文件加 (1) (2) 后缀避免覆盖
        copied = 0
        for f in notebooks + aux:
            dest_name = rename_map.get(f.name, f.name)
            dest = target / dest_name
            if dest.exists():
                stem, suffix = Path(dest_name).stem, Path(dest_name).suffix
                i = 1
                while dest.exists():
                    dest = target / f"{stem} ({i}){suffix}"
                    i += 1
            dest.write_bytes(f.read_bytes())
            copied += 1

        # 返回纠正信息，让调用方决定是否显示
        return True, "", renames


def is_valid_student_id(s: str) -> bool:
    """判断字符串是否是合法学号：至少 6 位纯数字开头"""
    return bool(re.match(r"^\d{6,}$", s))


def extract_all(overwrite: bool = False) -> tuple[list[str], list[tuple[str, str]]]:
    """解压所有新提交。返回 (成功学号列表, 跳过原因列表)

    逻辑：
      - 默认模式：有成绩就跳过
      - --overwrite：满分跳过；zip 没变 + 有成绩也跳过；zip 变了重解压
    """
    graded = get_graded_students()
    full_mark = get_full_mark_students() if overwrite else set()
    saved_hashes = load_zip_hashes()
    successes: list[str] = []
    skipped: list[tuple[str, str]] = []

    zip_files = sorted(SUBMITTED_DIR.glob("*.zip"))
    if not zip_files:
        return successes, skipped

    updated_hashes = dict(saved_hashes)

    for zip_path in zip_files:
        student_id = zip_path.stem

        # 跳过非学号的 zip（如导出的总包）
        if not is_valid_student_id(student_id):
            skipped.append((student_id, "非学号命名的 zip，跳过"))
            continue

        target = SUBMITTED_DIR / student_id / EXTRACT_SUBDIR

        # --overwrite 下满分直接跳过
        if overwrite and student_id in full_mark:
            skipped.append((student_id, "满分，跳过"))
            continue

        # 非 overwrite：有成绩就跳过
        if not overwrite and student_id in graded:
            skipped.append((student_id, "已有成绩"))
            continue

        # 计算当前 zip hash，判断内容是否变化
        zip_hash = compute_zip_hash(zip_path)
        zip_key = str(zip_path)
        hash_unchanged = saved_hashes.get(zip_key) == zip_hash

        # --overwrite 下：zip 没变 + 有成绩 → 跳过
        if overwrite and hash_unchanged and student_id in graded:
            skipped.append((student_id, "zip 未变，已有成绩，跳过"))
            updated_hashes[zip_key] = zip_hash
            continue

        # 已解压 + zip 没变 + 非 overwrite → 跳过
        if not overwrite and target.exists() and hash_unchanged:
            skipped.append((student_id, "zip 未变，已解压，跳过"))
            updated_hashes[zip_key] = zip_hash
            continue

        # 需要解压：先清掉旧解压目录（--overwrite 或首次）
        if target.exists():
            import shutil

            shutil.rmtree(target)

        ok, reason, renames = extract_submission(zip_path, target)
        if ok:
            successes.append(student_id)
            updated_hashes[zip_key] = zip_hash
            if renames:
                print(f"  ✓ {student_id}  （纠正文件名：{'，'.join(f'{old} → {new}' for old, new in renames)}）")
            else:
                print(f"  ✓ {student_id}")
        else:
            skipped.append((student_id, reason))
            print(f"  ⚠️  {student_id}: {reason}")
            # 清理空目录
            if target.exists():
                try:
                    target.rmdir()
                except OSError:
                    pass

    # 补齐缺失的 notebook（用 release 版），让 nbgrader 不因缺 notebook 报错
    release_dir = Path("release") / EXTRACT_SUBDIR
    expected_nbs = [f.name for f in release_dir.glob("*.ipynb")] if release_dir.exists() else []
    for sid in successes:
        target = SUBMITTED_DIR / sid / EXTRACT_SUBDIR
        for nb_name in expected_nbs:
            nb_path = target / nb_name
            if not nb_path.is_file():
                src = release_dir / nb_name
                if src.is_file():
                    nb_path.write_bytes(src.read_bytes())

    # 保存更新后的 hash 记录
    save_zip_hashes(updated_hashes)

    return successes, skipped


def clear_autograded(students: list[str]) -> None:
    """在 Docker 容器内删除学生的 autograded 目录（容器内是 root，无需 sudo）"""
    for sid in students:
        ag_path = f"/course/autograded/{sid}"
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{os.getcwd()}:/course",
            "nbgrader-math",
            "rm",
            "-rf",
            ag_path,
        ]
        subprocess.run(cmd, check=False, capture_output=True)


def run_grading(students: list[str]) -> int:
    """逐个调用 Docker 跑 nbgrader autograde（0.9.x 不支持逗号分隔多学生）"""
    print(f"\n=== 开始批改 ({len(students)} 人) ===")
    # 先清 autograded，避免 nbgrader 因目录已存在而跳过
    clear_autograded(students)
    failed: list[str] = []
    for sid in students:
        cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{os.getcwd()}:/course",
            "nbgrader-math",
            "nbgrader",
            "autograde",
            ASSIGNMENT,
            "--student",
            sid,
        ]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            failed.append(sid)
            print(f"  ✗ {sid} (退出码 {result.returncode})")
        else:
            print(f"  ✓ {sid}")

    if failed:
        print(f"\n批改失败 {len(failed)} 人: {', '.join(failed)}")
        return 1
    return 0


def get_full_mark_students() -> set[str]:
    """从数据库取本作业满分（最佳版本得分 == 满分 5）的学号"""
    if not Path(DB_PATH).exists():
        return set()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    try:
        # 每个 notebook 满分 5 分；学生有 Python/C 两个版本
        # 只要任一版本满分（得分 == 该版本满分）就算满分
        cur.execute(
            """
            SELECT st.id
            FROM grade g
            JOIN submitted_notebook sn ON g.notebook_id = sn.id
            JOIN submitted_assignment sa ON sn.assignment_id = sa.id
            JOIN student st ON sa.student_id = st.id
            JOIN assignment a ON sa.assignment_id = a.id
            JOIN grade_cells gc ON g.cell_id = gc.id
            WHERE a.name = ?
            GROUP BY st.id, sn.id
            HAVING ABS(SUM(g.auto_score) - SUM(gc.max_score)) < 1e-9;
            """,
            (ASSIGNMENT,),
        )
        return {row[0] for row in cur.fetchall()}
    except Exception:
        return set()
    finally:
        con.close()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="批改提交作业")
    parser.add_argument("--grade-only", action="store_true", help="仅批改，不解压")
    parser.add_argument("--overwrite", action="store_true", help="全部重新批改")
    args = parser.parse_args()

    skipped_all: list[tuple[str, str]] = []

    # ── 解压 ───────────────────────────────────────────────────────────────
    if not args.grade_only:
        print("=== 解压提交文件 ===")
        successes, skipped = extract_all(overwrite=args.overwrite)
        skipped_all.extend(skipped)
    else:
        # --grade-only：从 submitted 目录收集已有解压记录的学号
        overwrite = args.overwrite
        graded = get_graded_students()
        successes = []
        for d in sorted(SUBMITTED_DIR.iterdir()):
            if not d.is_dir():
                continue
            sid = d.name
            if not (d / EXTRACT_SUBDIR).is_dir():
                continue
            if not overwrite and sid in graded:
                skipped_all.append((sid, "已有成绩"))
                continue
            successes.append(sid)

    # ── 排除满分（即使 --overwrite 也不重判） ────────────────────────────
    if args.overwrite and successes:
        full_mark = get_full_mark_students()
        excluded = [sid for sid in successes if sid in full_mark]
        if excluded:
            successes = [sid for sid in successes if sid not in full_mark]
            skipped_all.extend([(sid, "满分，跳过") for sid in excluded])

    # ── 批改 ───────────────────────────────────────────────────────────────
    print()
    if not successes:
        print("=== 没有需要批改的提交 ===")
    else:
        print(f"=== 待批改学号 ({len(successes)} 人) ===")
        for sid in successes:
            print(f"  - {sid}")
        rc = run_grading(successes)
        if rc != 0:
            print(f"\n批改进程返回非零退出码: {rc}", file=sys.stderr)

    # ── 汇总跳过信息 ─────────────────────────────────────────────────────
    if skipped_all:
        print(f"\n=== 跳过的学号 ({len(skipped_all)} 人) ===")
        for sid, reason in skipped_all:
            print(f"  - {sid}: {reason}")

    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
