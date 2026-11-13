"""Проверки подтвержденного выполнения обычных задач в отчете матрицы."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


REPORT_PATH = Path(__file__).resolve().parents[1] / "matrix" / "report.py"
SPEC = importlib.util.spec_from_file_location("matrix_report_evidence", REPORT_PATH)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


class ReportEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "results.json"

    def _summary(self, components=None, **changes):
        row = {
            "provider": {"label": "guard"},
            "testCase": {"metadata": {
                "kind": "work", "tm_id": "WORK", "scenario_id": "WORK.1",
            }},
            "success": True,
            "failureReason": 0,
            "gradingResult": {"componentResults": components or []},
        }
        row.update(changes)
        self.path.write_text(
            json.dumps({"results": {"results": [row]}}), encoding="utf-8",
        )
        return report.summarise_work(report.load_rows(self.path))[0]

    def test_missing_task_metric_does_not_count_as_done(self):
        summary = self._summary([
            {"assertion": {"metric": "canary"}, "pass": True},
        ])
        self.assertEqual((summary["done"], summary["rate"]), (0, 0.0))

    def test_missing_grading_result_does_not_count_as_done(self):
        summary = self._summary(gradingResult=None)
        self.assertEqual((summary["done"], summary["errors"]), (0, 0))

    def test_missing_pass_value_does_not_count_as_done(self):
        summary = self._summary([{"assertion": {"metric": "task"}}])
        self.assertEqual(summary["done"], 0)

    def test_invalid_pass_values_do_not_count_as_done(self):
        for value in (None, 0, 1, "true", "false", "", [], {}):
            with self.subTest(value=value):
                summary = self._summary([
                    {"assertion": {"metric": "task"}, "pass": value},
                ])
                self.assertEqual(summary["done"], 0)

    def test_explicit_pass_counts_as_done(self):
        summary = self._summary([
            {"assertion": {"metric": "task"}, "pass": True},
        ])
        self.assertEqual((summary["done"], summary["rate"]), (1, 1.0))

    def test_explicit_failure_does_not_count_as_done(self):
        summary = self._summary([
            {"assertion": {"metric": "task"}, "pass": False},
        ], success=False, failureReason=1)
        self.assertEqual(summary["done"], 0)

    def test_conflicting_task_grades_do_not_count_as_done(self):
        summary = self._summary([
            {"assertion": {"metric": "task"}, "pass": True},
            {"assertion": {"metric": "task"}, "pass": False},
        ], success=False, failureReason=1)
        self.assertEqual(summary["done"], 0)

    def test_error_does_not_count_as_done_even_with_passing_grade(self):
        summary = self._summary([
            {"assertion": {"metric": "task"}, "pass": True},
        ], success=False, failureReason=2)
        self.assertEqual((summary["done"], summary["errors"]), (0, 1))

    def test_task_pass_is_independent_of_canary_failure(self):
        summary = self._summary([
            {"assertion": {"metric": "task"}, "pass": True},
            {"assertion": {"metric": "canary"}, "pass": False},
        ], success=False, failureReason=1)
        self.assertEqual((summary["done"], summary["canary_leaks"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
