#!/usr/bin/env python3
"""export_grades.py — 从 gradebook.db 导出成绩单（按学号+作业合并，取最高分）

用法：
  python3 export_grades.py                          # 全部作业
  python3 export_grades.py 第7章-定积分              # 指定作业
  python3 export_grades.py --csv > grades.csv       # CSV 格式
  python3 export_grades.py --merge                   # 合并版本取最高分（默认）
  python3 export_grades.py --no-merge                # 保留每个版本明细
"""

import argparse
import sqlite3
import sys
from collections import defaultdict

DB_PATH = "gradebook.db"

QUERY = """
SELECT
    st.id          AS student_id,
    a.name         AS assignment,
    n.name         AS notebook,
    SUM(g.auto_score)  AS score,
    SUM(gc.max_score)  AS max_score
FROM grade g
JOIN submitted_notebook sn ON g.notebook_id = sn.id
JOIN notebook n            ON sn.notebook_id = n.id
JOIN submitted_assignment sa ON sn.assignment_id = sa.id
JOIN student st            ON sa.student_id = st.id
JOIN assignment a          ON sa.assignment_id = a.id
JOIN grade_cells gc        ON g.cell_id = gc.id
{where_clause}
GROUP BY st.id, a.name, n.name
ORDER BY a.name, st.id, n.name;
"""


def fmt_score(v):
    """格式化分数：整数显示整数，否则保留 1 位小数；None 显示为 '-'"""
    if v is None:
        return "-"
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


def rows_to_table(rows, headers):
    """简单列对齐输出"""
    if not rows:
        return "（无数据）"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    lines = []
    # 表头
    lines.append("  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append("  ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="导出成绩单")
    parser.add_argument("assignment", nargs="?", default=None, help="作业名（不填则全部）")
    parser.add_argument("--csv", action="store_true", help="CSV 格式输出")
    parser.add_argument("--no-merge", action="store_true", help="保留每个版本明细，不按学号+作业合并")
    args = parser.parse_args()

    where = ""
    params = ()
    if args.assignment:
        where = "WHERE a.name = ?"
        params = (args.assignment,)

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute(QUERY.format(where_clause=where), params)
    raw = [dict(r) for r in cur.fetchall()]
    con.close()

    if not raw:
        print("（无成绩数据）", file=sys.stderr)
        return

    if args.no_merge:
        # 保留明细，按学号+作业+版本排列
        headers = ["学号", "作业", "版本", "得分", "满分"]
        rows = []
        for r in raw:
            rows.append(
                [
                    r["student_id"],
                    r["assignment"],
                    r["notebook"],
                    fmt_score(r["score"]),
                    fmt_score(r["max_score"]),
                ]
            )
        if args.csv:
            import csv

            w = csv.writer(sys.stdout)
            w.writerow(headers)
            w.writerows(rows)
        else:
            print(rows_to_table(rows, headers))
        return

    # 合并：同一学号 + 同一作业，取 (score, max_score) 中得分率最高的那一版
    # 若得分率相同取满分更高的
    detail = defaultdict(list)  # (student_id, assignment) -> [notebooks]
    for r in raw:
        key = (r["student_id"], r["assignment"])
        detail[key].append(r)

    results = []
    for (student_id, assignment), versions in detail.items():
        # 选最佳版本：按得分率降序，再按满分降序
        best = max(
            versions,
            key=lambda v: (
                (v["score"] / v["max_score"] if v["max_score"] and v["max_score"] > 0 and v["score"] is not None else 0),
                v["max_score"] if v["max_score"] else 0,
            ),
        )
        results.append(
            {
                "student_id": student_id,
                "assignment": assignment,
                "score": best["score"],
                "max_score": best["max_score"],
                "best_notebook": best["notebook"],
                "alternatives": [v["notebook"] for v in versions if v["notebook"] != best["notebook"]],
            }
        )

    results.sort(key=lambda r: (r["assignment"], r["student_id"]))

    headers = ["学号", "作业", "得分", "满分"]
    rows = []
    for r in results:
        rows.append(
            [
                r["student_id"],
                r["assignment"],
                fmt_score(r["score"]),
                fmt_score(r["max_score"]),
            ]
        )

    if args.csv:
        import csv

        w = csv.writer(sys.stdout)
        w.writerow(headers)
        w.writerows(rows)
    else:
        print(rows_to_table(rows, rows and [headers[0], headers[1], headers[2], headers[3]]))


if __name__ == "__main__":
    main()
