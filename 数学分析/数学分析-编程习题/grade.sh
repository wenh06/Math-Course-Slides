#!/usr/bin/env bash
# grade.sh — 批改 submitted/ 下所有 zip 提交
#
# 用法：
#   bash grade.sh            # 解压新提交并批改全部
#   bash grade.sh --grade-only   # 仅批改，不解压

set -euo pipefail

ASSIGNMENT="第7章-定积分"
SUBMITTED_DIR="submitted"
EXTRACT_SUBDIR="第7章-定积分"

only_grade=false
for arg in "$@"; do
    [[ "$arg" == "--grade-only" ]] && only_grade=true
done

if ! $only_grade; then
    echo "=== 解压提交文件 ==="
    found=0
    for zip in "$SUBMITTED_DIR"/*.zip; do
        [ -f "$zip" ] || continue
        student_id="$(basename "$zip" .zip)"
        target="$SUBMITTED_DIR/$student_id/$EXTRACT_SUBDIR"

        if [ -d "$target" ]; then
            echo "  跳过 $student_id（已解压）"
            continue
        fi

        echo "  解压 $student_id ..."
        tmpdir="$(mktemp -d)"
        unzip -q -o "$zip" -d "$tmpdir"

        mkdir -p "$target"
        # 如果 zip 里只有文件（没有目录层级），直接搬过来
        # 如果 zip 里已经有目录层级，展平一层
        if [ -d "$tmpdir/$EXTRACT_SUBDIR" ]; then
            mv "$tmpdir/$EXTRACT_SUBDIR"/* "$target/"
        else
            mv "$tmpdir"/* "$target/"
        fi
        rm -rf "$tmpdir"
        found=$((found + 1))
    done
    [[ $found -eq 0 ]] && echo "  没有新的 zip 需要解压"
fi

echo ""
echo "=== 开始批改 ==="
docker run --rm -v "$(pwd)":/course nbgrader-math \
    nbgrader autograde "$ASSIGNMENT"

echo ""
echo "=== 批改完成 ==="
