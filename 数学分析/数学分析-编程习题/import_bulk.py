#!/usr/bin/env python3
"""import_bulk.py — 从教学系统的批量导出包中复制各学生提交，放入 submitted/

用法：
  python3 import_bulk.py <bulk_zip_path>                # 默认：覆盖已有 zip
  python3 import_bulk.py <bulk_zip_path> --skip-existing # 跳过已存在的提交

教学系统导出的 zip 结构通常为：
  homework/
  ├── <学号1>_<学生名>/                           ← 目录名以学号开头
  │   ├── <学号1>_<学生名>_1_<学号1>.zip           ← 学生真正提交的压缩包
  │   └── <学号1>_<学生名>.htm
  ├── <学号2>_<学生名>/
  └── ...

本脚本：
  1. 遍历整个批量导出包的目录树，找到以学号开头的目录
  2. 在该目录下（仅一层）寻找恰好一个压缩文件（.zip/.rar/.7z/.tar.gz/...）
     - 零个 → 记录为"未提交"（不中断）
     - 多个 → 按启发式规则选一个（优先含 "_" 分隔的多段命名，其次最大）
  3. 判断选中的是不是合法 zip：
     - 是合法 zip → 原样复制到 submitted/<学号>.zip
     - 不是合法 zip（如 RAR5、7z）→ 检测格式，用 7z/unrar 解压后重打包为
       标准 zip，写入 submitted/<学号>.zip
  4. 最终核对：学生目录数 vs 有效提交数，报告缺交/转码失败的学生

解压、校验内容、写入 autograded 均由 grade.py 负责 —— grade.py 的
extract_all 会用 collect_submission_files 扫描整棵子树收集 .ipynb/.c/.h,
并用 hash 判断 zip 是否变化以决定是否重新解压。
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


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


# 常见压缩格式的文件头签名 → 格式名（用于检测实际格式）
_ARCHIVE_SIGNATURES: list[tuple[bytes, str]] = [
    (b"Rar!\x1a\x07\x01", "rar5"),  # RAR5
    (b"Rar!\x1a\x07\x00", "rar4"),  # RAR4
    (b"\x37\x7a\xbc\xaf\x27\x1c", "7z"),  # 7-Zip
    (b"PK\x03\x04", "zip"),  # ZIP
    (b"PK\x05\x06", "zip"),  # 空 ZIP
    (b"PK\x07\x08", "zip"),  # 分卷 ZIP
    (b"\x1f\x8b", "gzip"),  # gzip (tar.gz / tgz)
    (b"BZh", "bzip2"),  # bzip2 (tar.bz2)
    (b"\xfd7zXZ\x00", "xz"),  # xz (tar.xz)
]

# tar 格式的魔数在文件偏移 257 处
_TAR_OFFSET = 257
_TAR_MAGIC = b"ustar"


def detect_archive_format(path: str) -> str | None:
    """通过文件头签名检测压缩格式。返回格式名（zip/rar5/7z/gzip/...），无法识别返回 None。"""
    try:
        with open(path, "rb") as f:
            header = f.read(8)
            f.seek(_TAR_OFFSET)
            tail = f.read(5)
    except OSError:
        return None

    for sig, fmt in _ARCHIVE_SIGNATURES:
        if header.startswith(sig):
            return fmt
    if tail == _TAR_MAGIC:
        return "tar"
    return None


def _extract_archive(src_path: str, dest_dir: str, fmt: str | None) -> bool:
    """尝试解压压缩包到 dest_dir。成功返回 True，失败返回 False。

    策略：
      - 7z 优先（zip/7z/tar/*gz 等通吃）
      - RAR 且 7z 失败时回退到 unrar（p7zip 对 RAR5 支持不全）
    """
    # 第一次尝试：7z
    if shutil.which("7z"):
        r = subprocess.run(
            ["7z", "x", "-y", f"-o{dest_dir}", src_path],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return True
        # 只有 RAR 格式才值得用 unrar 再试，其他格式 7z 不支持就真的不支持
        if fmt not in ("rar4", "rar5"):
            err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "未知错误"
            print(f"    ⚠️  7z 解压失败: {err}")
            return False

    # 第二次尝试（仅 RAR）：unrar
    if fmt in ("rar4", "rar5") and shutil.which("unrar"):
        r = subprocess.run(
            ["unrar", "x", "-y", src_path, dest_dir + "/"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0:
            return True
        err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "未知错误"
        print(f"    ⚠️  unrar 解压失败: {err}")
        return False

    # 没有可用工具
    if not shutil.which("7z") and not shutil.which("unrar"):
        print("    ⚠️  系统未安装 7z/unrar，无法解压")
    return False


def convert_to_zip(src_path: str, dst_path: str) -> tuple[bool, str]:
    """把任意格式的压缩文件解压后重新打包为标准 zip。

    用系统 7z 解压（通吃 zip/rar/7z/tar/*gz 等），再用 Python zipfile 打包。
    返回 (是否成功, 描述信息)。
    """
    fmt = detect_archive_format(src_path) or "unknown"
    label = f"{os.path.basename(src_path)}（{fmt}）"

    with tempfile.TemporaryDirectory() as tmp:
        # 解压：优先用 7z，RAR 若 7z 不支持则回退到 unrar
        if not _extract_archive(src_path, tmp, fmt):
            return False, f"{label} — 解压失败（见上方错误）"

        # 重新打包为标准 zip
        try:
            with zipfile.ZipFile(dst_path, "w", zipfile.ZIP_DEFLATED) as zf:
                base = Path(tmp)
                for f in base.rglob("*"):
                    if f.is_file():
                        arcname = str(f.relative_to(base))
                        zf.write(f, arcname)
        except OSError as e:
            return False, f"{label} — 打包 zip 失败：{e}"

    return True, label


def build_zero_submission(target_path: str, release_dir: Path) -> bool:
    """把 release 版（无答案）打包为指定路径的 zip，作为"零分提交"。

    grade.py 解压后用 nbgrader autograde 批改，会得到 0 分。
    这样不用操作数据库，成绩由 autograde 正常产生。
    release_dir: 该作业对应的 release 目录（如 release/第7章-定积分/）。
    """
    if not release_dir.is_dir():
        print(f"    ⚠️  release 目录不存在: {release_dir}")
        return False

    files = [f for f in release_dir.rglob("*") if f.is_file()]
    if not files:
        print(f"    ⚠️  release 目录为空: {release_dir}")
        return False

    try:
        with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                arcname = str(f.relative_to(release_dir.parent))
                zf.write(f, arcname)
        return True
    except OSError as e:
        print(f"    ⚠️  打包 release 失败: {e}")
        return False


def import_bulk(
    bulk_zip: str,
    submitted_dir: str = "submitted",
    skip_existing: bool = False,
    release_dir: str | os.PathLike = "release/第7章-定积分",
) -> None:
    release = Path(release_dir)
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
        converted = 0  # 非 zip 格式转码为 zip 的人数
        zeroed = 0  # 用 release 版代替、将得 0 分的人数
        convert_failed = []  # 转码失败的 (学号, 原因)
        found_zip: set[str] = set()  # 目录下找到有效提交的学号
        missing: list[str] = []  # 有目录但无压缩文件的学号（未提交）

        # 教学系统可能导出各种压缩格式，这里列全一些
        _ARCHIVE_EXTS = (".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".txz")

        for sid in sorted(student_dirs):
            folder = student_dirs[sid]
            target_zip = os.path.join(submitted_dir, f"{sid}.zip")
            target_dir = os.path.join(submitted_dir, sid)

            # 在目录下（仅一层）找所有压缩文件（不限 .zip）
            archives = [
                os.path.join(folder, f)
                for f in os.listdir(folder)
                if f.lower().endswith(_ARCHIVE_EXTS) and os.path.isfile(os.path.join(folder, f))
            ]

            if not archives:
                # 有学生目录但无压缩文件 → 用 release 版代替，autograde 会判 0 分
                missing.append(sid)
                if not skip_existing or not (os.path.exists(target_zip) or os.path.exists(target_dir)):
                    if build_zero_submission(target_zip, release):
                        print(f"  ○ {sid} — 无提交，用 release 版代替（将得 0 分）")
                        zeroed += 1
                    else:
                        print(f"  ✗ {sid} — 无提交，且 release 版也不可用")
                else:
                    print(f"  跳过 {sid}（已存在）")
                    skipped += 1
                continue

            sub_archive = pick_zip(archives)

            if skip_existing and (os.path.exists(target_zip) or os.path.exists(target_dir)):
                print(f"  跳过 {sid}（已存在）")
                found_zip.add(sid)
                skipped += 1
                continue

            # 判断是不是合法 zip：是则原样复制；不是则检测格式并转码
            actual_fmt = detect_archive_format(sub_archive)
            is_valid_zip = actual_fmt == "zip" and zipfile.is_zipfile(sub_archive)

            if is_valid_zip:
                existed = os.path.exists(target_zip)
                shutil.copy2(sub_archive, target_zip)
                found_zip.add(sid)
                if existed:
                    print(f"  ↻ {sid} ← {os.path.basename(sub_archive)}（覆盖）")
                    overwritten += 1
                else:
                    print(f"  ✓ {sid} ← {os.path.basename(sub_archive)}")
                    copied += 1
            else:
                # 非 zip 格式（rar/7z/...）→ 解压后重打包为标准 zip
                ok, info = convert_to_zip(sub_archive, target_zip)
                if ok:
                    found_zip.add(sid)
                    print(f"  🔄 {sid} ← {info} → 转码为 zip")
                    converted += 1
                else:
                    # 转码也失败 → 用 release 版代替，判 0 分
                    convert_failed.append((sid, info))
                    if build_zero_submission(target_zip, release):
                        print("    → 改用 release 版代替（将得 0 分）")
                        zeroed += 1
                    print(f"  ✗ {sid} — {info}")

        # 汇总输出
        parts = []
        if copied:
            parts.append(f"新增 {copied} 个")
        if overwritten:
            parts.append(f"覆盖 {overwritten} 个")
        if converted:
            parts.append(f"转码 {converted} 个")
        if zeroed:
            parts.append(f"零分 {zeroed} 个")
        if skipped:
            parts.append(f"跳过 {skipped} 个")
        print(f"\n完成：{', '.join(parts) if parts else '无操作'}")

        if convert_failed:
            print(f"\n⚠️  {len(convert_failed)} 个转码失败（已用 release 版代替，得 0 分）：")
            for sid, reason in convert_failed:
                print(f"  - {sid}: {reason}")

        # ── 人数核对：学生目录数 vs 实际提交的 zip 数 ─────────────────────
        roster = len(student_dirs)
        submitted_count = len(found_zip) + zeroed
        print("\n=== 人数核对 ===")
        print(f"学生目录数（花名册）: {roster} 人")
        print(f"有效提交（可批改）: {submitted_count} 人")
        if missing:
            print(f"○  无提交、用 release 版代替（0 分）: {len(missing)} 人")
            for sid in missing:
                print(f"  - {sid}")
        if convert_failed:
            print(f"⚠️  转码失败、用 release 版代替（0 分）: {len(convert_failed)} 人")
            for sid, reason in convert_failed:
                print(f"  - {sid}: {reason}")
        if not missing and not convert_failed:
            print("✅ 人数一致，所有学生均有有效提交。")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="从教学系统批量导出 zip 中复制学生提交")
    parser.add_argument("bulk_zip", help="教学系统导出的批量 zip 文件路径")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过已存在的提交（默认：覆盖已有 zip，以便更新）",
    )
    parser.add_argument(
        "--release-dir",
        default="release/第7章-定积分",
        help="release 目录路径（默认：release/第7章-定积分）",
    )
    args = parser.parse_args()
    import_bulk(args.bulk_zip, skip_existing=args.skip_existing, release_dir=args.release_dir)
