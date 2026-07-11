#!/usr/bin/env bash
# grade.sh — 批改 submitted/ 下所有 zip 提交
#
# 用法：
#   bash grade.sh                # 解压新提交并批改（已有成绩的学号自动跳过）
#   bash grade.sh --grade-only   # 仅批改，不解压
#   bash grade.sh --overwrite    # 全部重新批改（忽略已有成绩）

set -euo pipefail

ASSIGNMENT="第7章-定积分"
SUBMITTED_DIR="submitted"
EXTRACT_SUBDIR="第7章-定积分"
DB="gradebook.db"

only_grade=false
overwrite=false
for arg in "$@"; do
    case "$arg" in
        --grade-only) only_grade=true ;;
        --overwrite)  overwrite=true ;;
    esac
done

# ── 解压 ───────────────────────────────────────────────────────────────────
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

# ── 确定要批改的学号 ───────────────────────────────────────────────────────
echo ""

if $overwrite; then
    echo "=== 全部重新批改 ==="
    student_args=()
else
    echo "=== 检查已有成绩 ==="
    # 从数据库取出已有本作业成绩的学号
    graded=$(sqlite3 "$DB" "
        SELECT DISTINCT st.id
        FROM grade g
        JOIN submitted_notebook sn ON g.notebook_id = sn.id
        JOIN submitted_assignment sa ON sn.assignment_id = sa.id
        JOIN student st ON sa.student_id = st.id
        JOIN assignment a ON sa.assignment_id = a.id
        WHERE a.name = '$ASSIGNMENT' AND g.auto_score IS NOT NULL;
    " 2>/dev/null || true)

    if [ -n "$graded" ]; then
        echo "  已批改学号："
        echo "$graded" | sed 's/^/    - /'
    fi

    # 收集 submitted 下所有学号，过滤掉已批改的
    student_args=()
    for dir in "$SUBMITTED_DIR"/*/; do
        [ -d "$dir" ] || continue
        student_id="$(basename "$dir")"
        # 检查该学号下是否有本作业的提交
        if [ ! -d "$dir/$EXTRACT_SUBDIR" ]; then
            continue
        fi
        # 检查是否已批改
        if echo "$graded" | grep -qx "$student_id"; then
            echo "  跳过 $student_id（已有成绩）"
            continue
        fi
        student_args+=("$student_id")
    done

    if [ ${#student_args[@]} -eq 0 ]; then
        echo ""
        echo "=== 没有需要批改的提交 ==="
        exit 0
    fi

    echo ""
    echo "=== 待批改学号 ==="
    printf '  - %s\n' "${student_args[@]}"
fi

# ── 批改 ───────────────────────────────────────────────────────────────────
echo ""
echo "=== 开始批改 ==="
if [ ${#student_args[@]} -eq 0 ]; then
    # 全部批改（--overwrite 或无待定学号时的全量）
    docker run --rm -v "$(pwd)":/course nbgrader-math \
        nbgrader autograde "$ASSIGNMENT"
else
    # 只批改指定学号（用 --student 过滤）
    docker run --rm -v "$(pwd)":/course nbgrader-math \
        nbgrader autograde "$ASSIGNMENT" --student "$(IFS=,; echo "${student_args[*]}")"
fi

echo ""
echo "=== 批改完成 ==="
