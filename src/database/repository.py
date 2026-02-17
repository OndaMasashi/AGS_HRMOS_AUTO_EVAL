"""データアクセス層 - 応募者・ドキュメント・マッチ結果のCRUD"""

import sqlite3
import uuid
from datetime import datetime
from typing import Optional


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # === scan_runs ===

    def create_scan_run(self) -> str:
        """新しいスキャン実行を開始し、IDを返す"""
        run_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO scan_runs (id, started_at, total_applicants, scanned_count, match_count, status) "
            "VALUES (?, ?, 0, 0, 0, 'running')",
            (run_id, datetime.now().isoformat()),
        )
        self.conn.commit()
        return run_id

    def complete_scan_run(self, run_id: str, total: int, scanned: int, matches: int):
        """スキャン実行を完了にする"""
        self.conn.execute(
            "UPDATE scan_runs SET completed_at = ?, total_applicants = ?, scanned_count = ?, "
            "match_count = ?, status = 'completed' WHERE id = ?",
            (datetime.now().isoformat(), total, scanned, matches, run_id),
        )
        self.conn.commit()

    def fail_scan_run(self, run_id: str):
        """スキャン実行を失敗にする"""
        self.conn.execute(
            "UPDATE scan_runs SET completed_at = ?, status = 'failed' WHERE id = ?",
            (datetime.now().isoformat(), run_id),
        )
        self.conn.commit()

    def get_scan_runs(self, limit: int = 10) -> list[dict]:
        """直近のスキャン実行履歴を取得"""
        rows = self.conn.execute(
            "SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # === applicants ===

    def upsert_applicant(self, applicant_id: str, name: str, page_url: str):
        """応募者を追加（既存なら名前・URLを更新）"""
        self.conn.execute(
            "INSERT INTO applicants (id, name, page_url) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name = excluded.name, page_url = excluded.page_url",
            (applicant_id, name, page_url),
        )
        self.conn.commit()

    def get_pending_applicants(self) -> list[dict]:
        """未スキャンの応募者を取得"""
        rows = self.conn.execute(
            "SELECT * FROM applicants WHERE status = 'pending' ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_applicants(self) -> list[dict]:
        """全応募者を取得"""
        rows = self.conn.execute(
            "SELECT * FROM applicants ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_applicant_scanned(self, applicant_id: str):
        """応募者をスキャン済みにする"""
        self.conn.execute(
            "UPDATE applicants SET status = 'scanned', scanned_at = ? WHERE id = ?",
            (datetime.now().isoformat(), applicant_id),
        )
        self.conn.commit()

    def mark_applicant_error(self, applicant_id: str):
        """応募者をエラー状態にする"""
        self.conn.execute(
            "UPDATE applicants SET status = 'error', scanned_at = ? WHERE id = ?",
            (datetime.now().isoformat(), applicant_id),
        )
        self.conn.commit()

    def reset_applicant_status(self, applicant_id: str):
        """応募者をpendingに戻す（再スキャン用）"""
        self.conn.execute(
            "UPDATE applicants SET status = 'pending', scanned_at = NULL WHERE id = ?",
            (applicant_id,),
        )
        self.conn.commit()

    def reset_all_applicants(self):
        """全応募者をpendingに戻す"""
        self.conn.execute("UPDATE applicants SET status = 'pending', scanned_at = NULL")
        self.conn.commit()

    def get_applicant_stats(self) -> dict:
        """応募者の統計を取得"""
        row = self.conn.execute(
            "SELECT "
            "  COUNT(*) as total, "
            "  SUM(CASE WHEN status = 'scanned' THEN 1 ELSE 0 END) as scanned, "
            "  SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending, "
            "  SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors "
            "FROM applicants"
        ).fetchone()
        return dict(row)

    # === documents ===

    def add_document(
        self, applicant_id: str, filename: str, file_type: str, file_path: str,
        parsed_text_length: int = 0
    ) -> int:
        """ドキュメントを追加し、IDを返す"""
        cursor = self.conn.execute(
            "INSERT INTO documents (applicant_id, filename, file_type, file_path, parsed_text_length) "
            "VALUES (?, ?, ?, ?, ?)",
            (applicant_id, filename, file_type, file_path, parsed_text_length),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_documents_for_applicant(self, applicant_id: str) -> list[dict]:
        """応募者のドキュメント一覧を取得"""
        rows = self.conn.execute(
            "SELECT * FROM documents WHERE applicant_id = ?", (applicant_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # === keyword_matches ===

    def add_match(
        self, applicant_id: str, document_id: int, keyword: str,
        context: str, scan_run_id: str
    ):
        """キーワードマッチを記録"""
        self.conn.execute(
            "INSERT INTO keyword_matches (applicant_id, document_id, keyword, context, scan_run_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (applicant_id, document_id, keyword, context, scan_run_id),
        )
        self.conn.commit()

    def get_matches_for_run(self, scan_run_id: str) -> list[dict]:
        """特定のスキャン実行のマッチ結果を取得"""
        rows = self.conn.execute(
            "SELECT km.*, a.name as applicant_name, a.page_url, d.filename "
            "FROM keyword_matches km "
            "JOIN applicants a ON km.applicant_id = a.id "
            "JOIN documents d ON km.document_id = d.id "
            "WHERE km.scan_run_id = ? "
            "ORDER BY a.name, km.keyword",
            (scan_run_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_matches(self) -> list[dict]:
        """全マッチ結果を取得"""
        rows = self.conn.execute(
            "SELECT km.*, a.name as applicant_name, a.page_url, d.filename "
            "FROM keyword_matches km "
            "JOIN applicants a ON km.applicant_id = a.id "
            "JOIN documents d ON km.document_id = d.id "
            "ORDER BY km.found_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_match_count_for_run(self, scan_run_id: str) -> int:
        """特定のスキャン実行のマッチ数を取得"""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM keyword_matches WHERE scan_run_id = ?",
            (scan_run_id,),
        ).fetchone()
        return row["cnt"]
