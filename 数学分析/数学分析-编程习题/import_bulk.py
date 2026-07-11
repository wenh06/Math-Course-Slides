#!/usr/bin/env python3
"""import_bulk.py — 从教学系统的批量导出 zip 中提取各学生提交，放入 submitted/

用法：
  python3 import_bulk.py <bulk_zip_path>

教学系统导出的 zip 结构通常为：
  homework/
  ├── <学号1>_<学生名>/          ← 学生名常被编码为乱码
  │   ├── <学号1>_<学生名>_1_<学号1>.zip  ← 学生真正提交的 zip
  │   └── <学号1>_<学生名>.htm
  ├── <学号2>_<学生名>/
  └── ...

本脚本：
  1. 解析目录名/文件名开头的数字串作为学号
  2. 找到学生提交（优先匹配「学号_…_1_学号.zip」模式，否则取目录下任意 .zip）
  3. 复制到 submitted/<学号>.zip
  4. 已有 <学号>.zip 或 <学号>/ 目录则跳过
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


def find_submission_zip(folder: str) -> str | None:
    """在学生目录中找到提交 zip 的路径，找不到返回 None"""
    if not os.path.isdir(folder):
        return None

    candidates = []
    for entry in os.listdir(folder):
        full = os.path.join(folder, entry)
        if not os.path.isfile(full):
            continue
        lower = entry.lower()
        if not lower.endswith(".zip"):
            continue
        # 判断是否是「提交 zip」：文件名含 "学号_..._学号.zip" 模式
        stem = entry  # 含扩展名
        sid_match = re.match(r"^(\d{6,})", stem)
        if sid_match:
            sid = sid_match.group(1)
            if re.search(rf"^{sid}.*_{sid}{{1,2}}_{sid}\.zip$", stem) or re.search(rf"^{sid}.*_{sid}\.zip$", stem):
                candidates.append(full)
        elif lower.endswith(".zip"):
            candidates.append(full)

    if not candidates:
        return None
    # 优先选最像「提交」的（含 _1_ 模式的），否则选最大的
    for c in candidates:
        if "_1_" in os.path.basename(c):
            return c
    # 没有一个匹配的，取体积最大的 zip
    return max(candidates, key=lambda p: os.path.getsize(p))


def import_bulk(bulk_zip: str, submitted_dir: str = "submitted") -> None:
    if not os.path.isfile(bulk_zip):
        print(f"文件不存在: {bulk_zip}", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        print(f"解压 {bulk_zip} ...")
        with zipfile.ZipFile(bulk_zip, "r") as zf:
            zf.extractall(tmp)

        # 找到所有学生目录（跳过非目录和非学号开头的）
        entries = []
        for root, dirs, files in os.walk(tmp):
            for d in dirs:
                sid = extract_student_id(d)
                if sid:
                    entries.append((sid, os.path.join(root, d)))
            break  # 只看第一层？继续往下找，因为有些嵌套

        # 如果第一层没找到（比如有 homework/ 包装层），往下钻一层
        if not entries:
            for root, dirs, files in os.walk(tmp):
                for d in dirs:
                    sid = extract_student_id(d)
                    if sid:
                        entries.append((sid, os.path.join(root, d)))

        if not entries:
            print("（未找到任何学生提交）")
            return

        # 去重：同一学号只取第一次出现
        seen = set()
        unique = []
        for sid, path in entries:
            if sid not in seen:
                seen.add(sid)
                unique.append((sid, path))

        print(f"发现 {len(unique)} 个学生目录\n")

        copied = 0
        skipped = 0
        for sid, folder in unique:
            target_zip = os.path.join(submitted_dir, f"{sid}.zip")
            target_dir = os.path.join(submitted_dir, sid)

            if os.path.exists(target_zip) or os.path.exists(target_dir):
                print(f"  跳过 {sid}（已存在）")
                skipped += 1
                continue

            sub_zip = find_submission_zip(folder)
            if sub_zip is None:
                print(f"  ⚠️  {sid} 未找到提交 zip，跳过")
                skipped += 1
                continue

            shutil.copy2(sub_zip, target_zip)
            print(f"  ✓ {sid} ← {os.path.basename(sub_zip)}")
            copied += 1

        print(f"\n完成：复制 {copied} 个，跳过 {skipped} 个")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 import_bulk.py <bulk_zip_path>")
        sys.exit(1)
    import_bulk(sys.argv[1])
