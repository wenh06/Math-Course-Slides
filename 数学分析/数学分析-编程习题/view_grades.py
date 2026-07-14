#!/usr/bin/env python3
"""view_grades.py — Streamlit 成绩查询页面

用法：
  streamlit run view_grades.py
"""

import os
import sqlite3
from datetime import datetime

import streamlit as st

DB_PATH = "gradebook.db"


def fmt_ts(ts: float) -> str:
    """把时间戳格式化为易读字符串"""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


@st.cache_resource
def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def query_grades(student_id: str):
    con = get_conn()
    cur = con.cursor()
    cur.execute(
        """
        SELECT
            a.name                          AS assignment,
            n.name                          AS notebook,
            SUM(g.auto_score)               AS score,
            SUM(gc.max_score)               AS max_score
        FROM grade g
        JOIN submitted_notebook sn ON g.notebook_id = sn.id
        JOIN notebook n            ON sn.notebook_id = n.id
        JOIN submitted_assignment sa ON sn.assignment_id = sa.id
        JOIN student st            ON sa.student_id = st.id
        JOIN assignment a          ON sa.assignment_id = a.id
        JOIN grade_cells gc        ON g.cell_id = gc.id
        WHERE st.id = ?
        GROUP BY a.name, n.name
        ORDER BY a.name, n.name;
        """,
        (student_id,),
    )
    return cur.fetchall()


def fmt_score(v):
    return f"{v:.0f}" if v == int(v) else f"{v:.1f}"


st.set_page_config(page_title="数学分析编程习题成绩查询", layout="centered")
st.title("数学分析编程习题 — 成绩查询")

# ── 成绩最后更新时间 ─────────────────────────────────────────────────
db_mtime = os.path.getmtime(DB_PATH)
st.markdown(
    f"> 🕗 **成绩最后更新：{fmt_ts(db_mtime)}**",
)
st.divider()

student_id = st.text_input("请输入学号：", placeholder="例如 2025310030313")

if student_id:
    rows = query_grades(student_id.strip())

    if not rows:
        st.warning("未提交或未批改")
    else:
        # 按作业合并，取最佳版本
        from collections import defaultdict

        by_assignment = defaultdict(list)
        for assignment, notebook, score, max_score in rows:
            by_assignment[assignment].append((notebook, score, max_score))

        for assignment, versions in by_assignment.items():
            best = max(
                versions,
                key=lambda v: (v[1] / v[2] if v[2] > 0 else 0, v[2]),
            )
            score_str = fmt_score(best[1])
            max_str = fmt_score(best[2])
            pct = best[1] / best[2] * 100 if best[2] > 0 else 0

            with st.container():
                col1, col2, col3 = st.columns([3, 2, 2])
                col1.metric(assignment, f"{score_str} / {max_str}")
                col2.caption(f"得分率：{pct:.0f}%")
                col3.caption(f"最佳版本：{best[0]}")

                if len(versions) > 1:
                    with st.expander("查看所有版本明细"):
                        for nb, sc, mx in versions:
                            st.write(f"- **{nb}**：{fmt_score(sc)} / {fmt_score(mx)}")
