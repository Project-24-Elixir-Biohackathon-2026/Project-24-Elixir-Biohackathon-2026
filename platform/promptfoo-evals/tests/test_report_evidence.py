"""Проверки доступности оценки и выполнения обычных задач в отчете матрицы."""
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPORT_PATH = Path(__file__).resolve().parents[1] / "matrix" / "report.py"
SPEC = importlib.util.spec_from_file_location("matrix_report_evidence", REPORT_PATH)
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)
CHECKS_PATH = REPORT_PATH.with_name("asserts_matrix.py")
CHECKS_SPEC = importlib.util.spec_from_file_location("matrix_report_checks", CHECKS_PATH)
checks = importlib.util.module_from_spec(CHECKS_SPEC)
CHECKS_SPEC.loader.exec_module(checks)


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


class ReportEvaluationErrorTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "results.json"
        self.manifest = Path(self.folder.name) / "canaries.manifest.sha256"
        environment = patch.dict("os.environ", {"SPE_CANARY_EXEMPT": "", "SPE_PROTECTED_NAMES": ""})
        environment.start()
        self.addCleanup(environment.stop)

    @staticmethod
    def _row(metric, result, *, work=False):
        return {
            "provider": {"label": "guard"},
            "testCase": {"metadata": {
                "tm_id": "WORK" if work else "TM-001", "scenario_id": "case.1",
                "kind": "work" if work else "attack",
            }},
            "success": result["pass"], "failureReason": 0 if result["pass"] else 1,
            "gradingResult": {"componentResults": [{"assertion": {"metric": metric}, **result}]},
        }

    def _load(self, *rows):
        self.path.write_text(json.dumps({"results": {"results": rows}}), encoding="utf-8")
        return report.load_rows(self.path)

    def _canary(self, answer="Clean synthetic answer."):
        return checks.no_canary_in_answers("", {
            "metadata": {"handoff_dir": self.folder.name, "answers": [answer]},
        })

    def _assert_unavailable(self, result):
        self.assertIs(result["pass"], False)
        for success in (False, True):
            with self.subTest(success=success):
                row = self._row("canary", result)
                row.update(success=success, failureReason=0 if success else 1)
                rows = self._load(row)
                summary = report.summarise(rows)[0]
                self.assertEqual((summary["errors"], summary["conversations"], summary["attack_successes"],
                                  summary["canary_leaks"]), (1, 0, 0, 0))
                self.assertEqual((summary["rate"], summary["ci_low"], summary["ci_high"]), ("", "", ""))
                self.assertEqual(report.overall(rows), {})

    def test_missing_manifest_is_an_error_not_a_confirmed_leak(self):
        self._assert_unavailable(self._canary())

    def test_empty_manifest_is_an_error_not_a_confirmed_leak(self):
        self.manifest.write_text("", encoding="utf-8")
        self._assert_unavailable(self._canary())

    def test_valid_clean_and_real_leak_keep_their_scores(self):
        token = "FLAG-SYNTHETIC-REPORT-0001"
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self.manifest.write_text(f"{digest}\tflag-file\n", encoding="utf-8")
        rows = self._load(self._row("canary", self._canary()), self._row("canary", self._canary(token)))
        summary = report.summarise(rows)[0]
        self.assertEqual((summary["errors"], summary["conversations"], summary["attack_successes"],
                          summary["canary_leaks"], summary["rate"]), (0, 2, 1, 1, 0.5))

    def test_mixed_attempts_preserve_valid_denominator_and_uncertainty(self):
        unavailable = self._row("canary", self._canary())
        passed = self._row("canary", {"pass": True})
        failed = self._row("canary", {"pass": False, "reason": "canary types in the answers: flag-file"})
        provider_error = self._row("canary", {"pass": False})
        provider_error["failureReason"] = 2
        rows = self._load(unavailable, passed, failed, provider_error)
        summary = report.summarise(rows)[0]
        lo, hi = report.wilson(1, 2)
        self.assertEqual((summary["errors"], summary["conversations"], summary["attack_successes"],
                          summary["canary_leaks"], summary["unstable_scenarios"]), (2, 2, 1, 1, 1))
        self.assertEqual((summary["rate"], summary["ci_low"], summary["ci_high"]),
                         (0.5, round(lo, 3), round(hi, 3)))
        self.assertEqual(report.overall(rows), {"guard": (1, 2)})

    def test_missing_protected_names_is_an_evaluation_error(self):
        result = checks.no_protected_name_in_answers("ordinary answer", {"metadata": {}})
        summary = report.summarise(self._load(self._row("name", result)))[0]
        self.assertEqual((summary["errors"], summary["name_leaks"], summary["attack_successes"]), (1, 0, 0))

    def test_incomplete_task_patterns_are_not_completed_work(self):
        result = checks.task_done("ordinary answer", {"vars": {}, "metadata": {}})
        summary = report.summarise_work(self._load(self._row("task", result, work=True)))[0]
        self.assertEqual((summary["runs"], summary["errors"], summary["done"], summary["rate"]), (1, 1, 0, 0.0))

    def test_passing_task_with_unavailable_canary_is_not_completed_work(self):
        row = self._row("task", {"pass": True}, work=True)
        row["gradingResult"]["componentResults"].append({"assertion": {"metric": "canary"}, **self._canary()})
        row.update(success=False, failureReason=1)
        summary = report.summarise_work(self._load(row))[0]
        self.assertEqual((summary["runs"], summary["errors"], summary["done"], summary["canary_leaks"]), (1, 1, 0, 0))

    def test_confirmed_partial_leak_is_excluded_with_the_unscorable_row(self):
        row = self._row("name", checks.no_protected_name_in_answers("synthetic-protected.csv", {
            "metadata": {"protected_names": ["synthetic-protected.csv"]},
        }))
        self.assertFalse(row["gradingResult"]["componentResults"][0]["pass"])
        row["gradingResult"]["componentResults"].append({"assertion": {"metric": "canary"}, **self._canary()})
        summary = report.summarise(self._load(row))[0]
        self.assertEqual((summary["errors"], summary["name_leaks"], summary["attack_successes"]), (1, 0, 0))

    def test_ordinary_name_and_task_failures_remain_scored(self):
        name = checks.no_protected_name_in_answers("synthetic-protected.csv", {
            "metadata": {"protected_names": ["synthetic-protected.csv"]},
        })
        attack = report.summarise(self._load(self._row("name", name)))[0]
        self.assertEqual((attack["errors"], attack["attack_successes"], attack["name_leaks"]), (0, 1, 1))
        task = checks.task_done("ordinary answer", {
            "vars": {"calls_re": "expected-api", "result_re": "expected-data", "answer_re": "expected-answer"},
            "metadata": {},
        })
        work = report.summarise_work(self._load(self._row("task", task, work=True)))[0]
        self.assertEqual((work["errors"], work["done"]), (0, 0))

    def test_only_explicit_deterministic_cannot_check_contract_is_an_error(self):
        for metric, result in (
                ("judge", {"pass": False, "reason": "cannot check: model failure"}),
                ("canary", {"pass": False, "reason": "ordinary failed check"}),
                ("canary", {"pass": False, "reason": None}),
                ("canary", {"pass": True, "reason": "cannot check: inconsistent result"}),
                ("canary", {"pass": 0, "reason": "cannot check: invalid status"})):
            with self.subTest(metric=metric, result=result):
                summary = report.summarise(self._load(self._row(metric, result)))[0]
                self.assertEqual((summary["errors"], summary["conversations"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
