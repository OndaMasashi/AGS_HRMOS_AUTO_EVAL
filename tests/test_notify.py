"""結果メールの「評価できなかった応募者」表示のユニットテスト

評価できなかった応募者は status='error' になり、通常の scan では再評価されない。
結果メールに出ないと誰にも気づかれずに残る（2026-09-16/17 に HRMOS の
リマインダーで初めて発覚した）ため、表示が消えないよう固定しておく。
"""

from unittest.mock import patch

from src.reporter import notify
from src.reporter.notify import _build_failed_html, _build_html

FAILED = [{
    "name": "試験 太郎",
    "page_url": "https://hrmos.co/interviews/screening/1?jobId=2&screeningId=3",
    "reason": "AIの応答を評価結果として読めなかった（評価を断った可能性）",
}]


class TestFailedApplicantsHtml:
    def test_lists_name_reason_and_link(self):
        body = _build_failed_html(FAILED)
        assert "評価できなかった応募者 1名" in body
        assert "試験 太郎" in body
        assert "評価を断った可能性" in body
        assert "href='https://hrmos.co/interviews/screening/1?jobId=2&amp;screeningId=3'" in body

    def test_escapes_name(self):
        body = _build_failed_html([{"name": "<b>x</b>", "page_url": "", "reason": "r"}])
        assert "<b>x</b>" not in body
        assert "&lt;b&gt;x&lt;/b&gt;" in body

    def test_empty_renders_nothing(self):
        assert _build_failed_html([]) == ""

    def test_included_in_report_body(self):
        body = _build_html([], ["項目A"], 5, 1, "2026-09-21", [], "", FAILED)
        assert "評価できなかった応募者 1名" in body


class TestReportSubject:
    def _subject(self, failed):
        with patch.object(notify, "_resolve_email_settings", return_value={"prefix": "[HRMOS]"}), \
             patch.object(notify, "_send_email", return_value=True) as send:
            notify.send_report_email(
                [], ["項目A"], "no_such.xlsx", {}, 5, 1, failed_applicants=failed,
            )
        return send.call_args.args[1]

    def test_subject_counts_failed(self):
        assert "評価できず 1名" in self._subject(FAILED)

    def test_subject_unchanged_without_failed(self):
        assert "評価できず" not in self._subject([])
