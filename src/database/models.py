"""SQLiteデータベースのスキーマ定義・初期化"""

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS applicants (
    id TEXT PRIMARY KEY,
    name TEXT,
    page_url TEXT,
    status TEXT DEFAULT 'pending',
    scanned_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hrmos_eval_status TEXT,
    hrmos_eval_at TIMESTAMP,
    applied_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id TEXT REFERENCES applicants(id),
    filename TEXT,
    file_type TEXT,
    file_path TEXT,
    parsed_text_length INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS keyword_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id TEXT REFERENCES applicants(id),
    document_id INTEGER REFERENCES documents(id),
    keyword TEXT,
    context TEXT,
    scan_run_id TEXT,
    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id TEXT PRIMARY KEY,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    total_applicants INTEGER,
    scanned_count INTEGER,
    match_count INTEGER,
    status TEXT
);

CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    applicant_id TEXT REFERENCES applicants(id),
    document_id INTEGER REFERENCES documents(id),
    criteria_name TEXT,
    score INTEGER,
    comment TEXT,
    total_score INTEGER,
    overall_comment TEXT,
    interview_questions TEXT,
    applicant_gender TEXT,
    applicant_age INTEGER,
    remarks TEXT,
    scan_run_id TEXT,
    raw_response TEXT,
    evaluated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _migrate_evaluations(conn: sqlite3.Connection):
    """既存DBのevaluationsテーブルにカラムを追加（マイグレーション）"""
    cursor = conn.execute("PRAGMA table_info(evaluations)")
    columns = {row[1] for row in cursor.fetchall()}
    if "applicant_gender" not in columns:
        conn.execute("ALTER TABLE evaluations ADD COLUMN applicant_gender TEXT")
    if "applicant_age" not in columns:
        conn.execute("ALTER TABLE evaluations ADD COLUMN applicant_age INTEGER")
    if "remarks" not in columns:
        conn.execute("ALTER TABLE evaluations ADD COLUMN remarks TEXT")
    conn.commit()


def _migrate_applicants(conn: sqlite3.Connection):
    """既存DBのapplicantsテーブルにカラムを追加（マイグレーション）

    HRMOS への自動NG評価登録の実施状況を持つ。二重登録を防ぐ唯一の記録先で、
    HRMOS 側は同じ応募者への評価登録を何度でも受け付けるため、ここが欠けると
    再実行のたびにタイムラインへ評価が積み増される。
    """
    cursor = conn.execute("PRAGMA table_info(applicants)")
    columns = {row[1] for row in cursor.fetchall()}
    if "hrmos_eval_status" not in columns:
        conn.execute("ALTER TABLE applicants ADD COLUMN hrmos_eval_status TEXT")
    if "hrmos_eval_at" not in columns:
        conn.execute("ALTER TABLE applicants ADD COLUMN hrmos_eval_at TIMESTAMP")
    if "applied_at" not in columns:
        conn.execute("ALTER TABLE applicants ADD COLUMN applied_at TIMESTAMP")
    conn.commit()


def init_db(db_path: str) -> sqlite3.Connection:
    """データベースを初期化し、接続を返す"""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    _migrate_evaluations(conn)
    _migrate_applicants(conn)
    conn.commit()
    return conn
