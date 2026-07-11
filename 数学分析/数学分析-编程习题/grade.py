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


def find_notebook_dir(root: Path) -> Path | None:
    """在 root 下定位包含目标 notebook 的目录，找不到返回 None。
    返回的目录中应包含至少一个 .ipynb 文件（最终可执行 grading 的 notebook）。"""

    def is_junk(path: Path) -> bool:
        return "__MACOSX" in path.parts

    def has_real_notebook(dir_path: Path) -> bool:
        return any(f.suffix == ".ipynb" and f.is_file() for f in dir_path.iterdir())

    # 优先：直接子目录 == EXTRACT_SUBDIR
    direct = root / EXTRACT_SUBDIR
    if direct.is_dir() and has_real_notebook(direct):
        return direct

    # 递归：找包含 "*第6节*.ipynb" 的目录（排除系统垃圾）
    for nb in root.rglob("*第6节*.ipynb"):
        if is_junk(nb):
            continue
        # 如果在 .ipynb_checkpoints 里且外面有同名 notebook → 用外面那个
        if ".ipynb_checkpoints" in nb.parts:
            # 看看外层有没有真正的 notebook
            outer = nb.parent.parent / nb.name.replace("-checkpoint", "")
            if outer.is_file():
                return nb.parent.parent
            continue  # 否则跳过 checkpoint
        return nb.parent

    # 兜底 1：找任意 .ipynb 的目录（排除 checkpoints + 垃圾）
    for nb in root.rglob("*.ipynb"):
        if is_junk(nb) or ".ipynb_checkpoints" in nb.parts:
            continue
        return nb.parent

    # 兜底 2：如果只剩 checkpoint 文件，也算（比完全没有好）
    for nb in root.rglob("*.ipynb"):
        if is_junk(nb):
            continue
        return nb.parent

    return None


def extract_submission(zip_path: Path, target: Path) -> tuple[bool, str]:
    """解压单个学生提交到 target。返回 (是否成功, 失败原因)"""
    target.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_path)
        except zipfile.BadZipFile:
            return False, "zip 文件损坏"

        src_dir = find_notebook_dir(tmp_path)
        if src_dir is None:
            # 打印 zip 内部结构供排查
            names = []
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    if not info.is_dir():
                        names.append(info.filename)
            return False, f"未找到 .ipynb 文件，zip 内容：{names[:10]}"

        # 只复制需要的文件
        copied = 0
        for f in src_dir.iterdir():
            if f.suffix in (".ipynb", ".c", ".h") and f.is_file():
                (target / f.name).write_bytes(f.read_bytes())
                copied += 1

        if copied == 0:
            return False, "未提取到有效文件"

        return True, ""


def is_valid_student_id(s: str) -> bool:
    """判断字符串是否是合法学号：至少 6 位纯数字开头"""
    return bool(re.match(r"^\d{6,}$", s))


def extract_all(overwrite: bool = False) -> tuple[list[str], list[tuple[str, str]]]:
    """解压所有新提交。返回 (成功学号列表, 跳过原因列表)"""
    graded = get_graded_students()
    successes: list[str] = []
    skipped: list[tuple[str, str]] = []

    zip_files = sorted(SUBMITTED_DIR.glob("*.zip"))
    if not zip_files:
        return successes, skipped

    for zip_path in zip_files:
        student_id = zip_path.stem

        # 跳过非学号的 zip（如导出的总包）
        if not is_valid_student_id(student_id):
            skipped.append((student_id, "非学号命名的 zip，跳过"))
            continue

        target = SUBMITTED_DIR / student_id / EXTRACT_SUBDIR

        if not overwrite and student_id in graded:
            skipped.append((student_id, "已有成绩"))
            continue

        if target.exists():
            # 已解压过，算成功（进入批改队列）
            if not overwrite and student_id in graded:
                skipped.append((student_id, "已有成绩"))
            else:
                successes.append(student_id)
            continue

        ok, reason = extract_submission(zip_path, target)
        if ok:
            successes.append(student_id)
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

    return successes, skipped


def run_grading(students: list[str]) -> int:
    """逐个调用 Docker 跑 nbgrader autograde（0.9.x 不支持逗号分隔多学生）"""
    print(f"\n=== 开始批改 ({len(students)} 人) ===")
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
