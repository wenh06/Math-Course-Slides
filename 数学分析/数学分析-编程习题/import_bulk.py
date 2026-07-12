#!/usr/bin/env python3
"""import_bulk.py — 从教学系统的批量导出 zip 中复制各学生提交，放入 submitted/

用法：
  python3 import_bulk.py <bulk_zip_path>                # 默认：覆盖已有 zip
  python3 import_bulk.py <bulk_zip_path> --skip-existing # 跳过已存在的提交

教学系统导出的 zip 结构通常为：
  homework/
  ├── <学号1>_<学生名>/                           ← 目录名以学号开头
  │   ├── <学号1>_<学生名>_1_<学号1>.zip           ← 学生真正提交的 zip
  │   └── <学号1>_<学生名>.htm
  ├── <学号2>_<学生名>/
  └── ...

本脚本：
  1. 遍历整个批量导出 zip 的目录树，找到以学号开头的目录
  2. 在该目录下（仅一层）寻找恰好一个 .zip 文件
     - 零个 → 报错（说明学生没提交或结构异常）
     - 多个 → 按启发式规则选一个（优先含 "_" 分隔的多段命名，其次最大）
  3. 原样复制到 submitted/<学号>.zip（不检查内容，不解压，不读文件名）

解压、校验内容、写入 autograded 均由 grade.py 负责 —— grade.py 的
extract_all 会用 collect_submission_files 扫描整棵子树收集 .ipynb/.c/.h,
并用 hash 判断 zip 是否变化以决定是否重新解压。
"""

import os
import re
import shutil
import sys
import tempfile
import zipfile


def extract_student_id(name: str) -> str | None:
    """从名字中提取学号：开头的连续数字"""
    m = re.match(r"^(\d{6,})", name)
    return m.group(1) if m else None


def pick_zip(zips: list[str]) -> str:
    """从一个学生目录中找到的多个 zip 中选一个最像正式提交的"""
    if len(zips) == 1:
        return zips[0]
    # 优先含多段命名（如 xxx_xxx_1_xxx.zip）的
    for z in zips:
        base = os.path.basename(z)
        if re.search(r"^\d{6,}_.+_.+_\d{6,}$", base):
            return z
    # 其次选最大的
    return max(zips, key=lambda p: os.path.getsize(p))


def import_bulk(bulk_zip: str, submitted_dir: str = "submitted", skip_existing: bool = False) -> None:
    if not os.path.isfile(bulk_zip):
        print(f"文件不存在: {bulk_zip}", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"解压 {bulk_zip} ...")
        with zipfile.ZipFile(bulk_zip, "r") as zf:
            zf.extractall(tmp)

        # 整个目录树中找所有以学号开头的目录（保留最上层）
        student_dirs: dict[str, str] = {}
        for root, dirs, _ in os.walk(tmp):
            for d in dirs:
                sid = extract_student_id(d)
                if sid:
                    full = os.path.join(root, d)
                    if sid not in student_dirs:
                        student_dirs[sid] = full
                    else:
                        # 已有记录，保留更上层的（路径更短的）
                        if len(full) < len(student_dirs[sid]):
                            student_dirs[sid] = full

        if not student_dirs:
            print("（未找到任何学生提交）")
            return

        print(f"发现 {len(student_dirs)} 个学生目录\n")

        copied = 0
        overwritten = 0
        skipped = 0
        errors: list[tuple[str, str]] = []

        for sid in sorted(student_dirs):
            folder = student_dirs[sid]
            target_zip = os.path.join(submitted_dir, f"{sid}.zip")
            target_dir = os.path.join(submitted_dir, sid)

            if skip_existing and (os.path.exists(target_zip) or os.path.exists(target_dir)):
                print(f"  跳过 {sid}（已存在）")
                skipped += 1
                continue

            # 在目录下（仅一层）找所有 .zip 文件
            zips = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith(".zip") and os.path.isfile(os.path.join(folder, f))
            ]

            if not zips:
                errors.append((sid, f"目录 {os.path.basename(folder)} 下未找到 .zip 文件"))
                print(f"  ✗ {sid} — 目录下无 .zip")
                continue

            sub_zip = pick_zip(zips)
            existed = os.path.exists(target_zip)
            shutil.copy2(sub_zip, target_zip)
            if existed:
                print(f"  ↻ {sid} ← {os.path.basename(sub_zip)}（覆盖）")
                overwritten += 1
            else:
                print(f"  ✓ {sid} ← {os.path.basename(sub_zip)}")
                copied += 1

        # 汇总输出
        parts = []
        if copied:
            parts.append(f"新增 {copied} 个")
        if overwritten:
            parts.append(f"覆盖 {overwritten} 个")
        if skipped:
            parts.append(f"跳过 {skipped} 个")
        print(f"\n完成：{', '.join(parts) if parts else '无操作'}")

        if errors:
            print(f"\n⚠️  {len(errors)} 个错误：")
            for sid, reason in errors:
                print(f"  - {sid}: {reason}")
            sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="从教学系统批量导出 zip 中复制学生提交")
    parser.add_argument("bulk_zip", help="教学系统导出的批量 zip 文件路径")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过已存在的提交（默认：覆盖已有 zip，以便更新）",
    )
    args = parser.parse_args()
    import_bulk(args.bulk_zip, skip_existing=args.skip_existing)
