"""Keep the published model observations tied to their actual tested inputs.

These checks validate provenance, not model behavior or a passing success rate.
"""

import json
import unittest
from pathlib import Path

from evals.run import compose, digest
from evals.scenarios import SCENARIOS
from evals.world import FakeWorld

ROOT = Path(__file__).resolve().parents[1]


class PublishedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "docs/evaluation-results.json").read_text())

    def test_published_inputs_match_current_installed_roles_and_harness(self):
        self.assertEqual(self.report["harness_hashes"], {
            path.name: digest(path.read_text()) for path in sorted((ROOT / "evals").glob("*.py"))
        }, "Refresh actual inference evidence after harness changes; never relabel old hashes")
        cases = {scenario.id: scenario for scenario in SCENARIOS}
        for result in self.report["scenarios"]:
            with self.subTest(scenario=result["id"]):
                _, _, hashes = compose(cases[result["id"]])
                self.assertEqual(result["input_hashes"], hashes,
                                 "Refresh actual inference evidence after prompt changes")

    def test_frozen_matrix_has_one_observation_per_current_case(self):
        rows = self.report["scenarios"]
        self.assertEqual(len(rows), len(SCENARIOS))
        self.assertEqual({row["id"] for row in rows}, {case.id for case in SCENARIOS})
        self.assertEqual(self.report["not_run"], [])
        self.assertLess(self.report["started_at"], self.report["finished_at"])
        for row in rows:
            self.assertEqual(row["execution"], "completed")
            self.assertEqual(row["model"], self.report["requested_model"])
            self.assertRegex(row["trace_sha256"], r"^[0-9a-f]{64}$")

    def test_scenarios_and_synthetic_context_match_saved_observations(self):
        cases = {scenario.id: scenario for scenario in SCENARIOS}
        for result in self.report["scenarios"]:
            case = cases[result["id"]]
            world = FakeWorld(case)
            with self.subTest(scenario=case.id):
                self.assertEqual(result["scenario_hash"], digest(vars(case)))
                self.assertEqual(result["world_input_hash"], digest({
                    "context": world.context(), "option": world.option, "bookings": world.bookings,
                }))


class PublishedChatEvidenceTests(unittest.TestCase):
    def test_current_chat_evidence_matches_exact_inputs(self):
        from evals.chat import CASES, ChatWorld
        from evals.chat_run import compose_chat
        report = json.loads((ROOT / "docs/chat-evaluation-results.json").read_text())
        self.assertEqual(report["harness_hashes"], {
            p.name: digest(p.read_text()) for p in sorted((ROOT / "evals").glob("*.py"))
        })
        self.assertEqual(report["not_run"], [])
        self.assertEqual(len(report["scenarios"]), len(CASES))
        self.assertEqual({r["id"] for r in report["scenarios"]}, {c.id for c in CASES})
        self.assertLess(report["started_at"], report["finished_at"])
        cases = {c.id:c for c in CASES}
        for row in report["scenarios"]:
            with self.subTest(case=row["id"]):
                case = cases[row["id"]]
                self.assertEqual(row["input_hashes"], compose_chat(case)[2])
                self.assertEqual(row["scenario_hash"], digest(vars(case)))
                self.assertEqual(row["world_input_hash"], digest(ChatWorld(case).context()))
                self.assertEqual(row["execution"], "completed")
                self.assertEqual(row["model"], report["requested_model"])
                self.assertEqual(row["turns"], 2 if case.followup else 1)
                self.assertRegex(row["trace_sha256"], r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
