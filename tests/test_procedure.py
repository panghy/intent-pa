"""Packaging and synthetic record checks, not tests of model decision behavior."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_pack import BOOKING_ROLES, EXPECTED_IDS, load_procedures, parse_generated
from check_intent_parser import fixture_source


class InstalledProcedureTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pa-installed-procedure-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.installed = self.root / "specialists"
        shutil.copytree(ROOT / "specialists", self.installed)
        self.procedure = load_procedures(ROOT)["appointment-booking"]["body"]

    def test_discovery_and_loading_from_specialists_only_copy(self):
        self.assertEqual({path.name for path in self.root.iterdir()}, {"specialists"})
        loaded = {}
        for path in sorted(self.installed.glob("*.md")):
            metadata, body = parse_generated(path.read_text(encoding="utf-8"))
            loaded[path.stem] = (metadata, body)
        self.assertEqual(set(loaded), EXPECTED_IDS)
        self.assertEqual(set(loaded["pa-ada"][0]["teamAgents"]), EXPECTED_IDS - {"pa-ada"})
        for identifier in BOOKING_ROLES:
            self.assertEqual(loaded[identifier][1].count(self.procedure), 1)
            self.assertIn("## 8. Handoff and cleanup on every exit", loaded[identifier][1])

    @unittest.skipUnless(os.environ.get("INTENT_SPECIALISTS_SOURCE"),
                         "Optional actual-parser check needs INTENT_SPECIALISTS_SOURCE and cached Cargo dependencies")
    def test_actual_intent_parser_loads_installed_procedure_without_sources(self):
        source = Path(os.environ["INTENT_SPECIALISTS_SOURCE"]).read_text(encoding="utf-8")
        fixture = self.root / "parser"
        (fixture / "src").mkdir(parents=True)
        (fixture / "Cargo.toml").write_text(
            '[package]\nname = "installed-procedure-test"\nversion = "0.1.0"\nedition = "2021"\n'
            '[dependencies]\nserde_json = "1"\n', encoding="utf-8")
        (fixture / "src/main.rs").write_text(fixture_source(source), encoding="utf-8")
        result = subprocess.run(
            ["cargo", "run", "--offline", "--quiet", "--manifest-path", str(fixture / "Cargo.toml"),
             "--", *map(str, sorted(self.installed.glob("*.md")))],
            cwd=self.installed, env=dict(os.environ, CARGO_TARGET_DIR=str(fixture / "target")),
            text=True, capture_output=True, timeout=120, check=True,
        )
        loaded = json.loads(result.stdout)
        self.assertEqual({item["id"] for item in loaded}, EXPECTED_IDS)
        for item in loaded:
            with self.subTest(identifier=item["id"]):
                metadata, body = parse_generated((self.installed / f"{item['id']}.md").read_text())
                self.assertEqual(item["metadata"], metadata)
                self.assertEqual(item["prompt"], body)
                if item["id"] in BOOKING_ROLES:
                    self.assertEqual(item["prompt"].count(self.procedure), 1)


class ProcedureFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((ROOT / "tests/fixtures/appointment_procedure.json").read_text())

    def test_fixture_version_matches_installed_procedure(self):
        identifier = self.fixture["procedure_id"]
        procedure = load_procedures(ROOT)[identifier]["body"]
        self.assertIn(f"Procedure version: {self.fixture['procedure_version']}\n", procedure)

    def test_unknown_write_example_reconciles_the_original_identity(self):
        booking = self.fixture["booking"]
        write, lookup = booking["attempts"]
        self.assertEqual(write["operation"], "booking_create")
        self.assertEqual(write["outcome"], "outcome-unknown")
        self.assertEqual(lookup["operation"], "booking_lookup")
        self.assertEqual(write["arguments"]["request_id"], booking["request_id"])
        self.assertEqual(lookup["arguments"]["request_id"], booking["request_id"])
        self.assertEqual(write["arguments"]["idempotency_key"], booking["idempotency_key"])
        evidence = booking["provider_evidence"]
        self.assertEqual(evidence["request_id"], booking["request_id"])
        self.assertEqual(evidence["booking_id"], lookup["booking_id"])
        self.assertEqual(evidence["evidence_id"], lookup["evidence_id"])
        self.assertEqual(evidence["option_id"], write["arguments"]["option_id"])
        self.assertEqual(evidence["status"], lookup["outcome"])
        self.assertEqual(booking["reply"]["evidence_id"], evidence["evidence_id"])

    def test_example_authority_and_freshness_match_the_recorded_write(self):
        booking = self.fixture["booking"]
        authority, option, write = booking["authorization"], booking["option"], booking["attempts"][0]
        self.assertEqual(authority["task_version"], booking["task_version"])
        self.assertFalse(authority["revoked"])
        for field in ("option_id", "terms_version"):
            self.assertEqual(authority[field], option[field])
            self.assertEqual(option[field], write["arguments"][field])
        self.assertEqual(authority["currency"], option["currency"])
        self.assertLessEqual(option["total_minor"], authority["maximum_total_minor"])
        # Python 3.10 requires an explicit UTC offset instead of the Z suffix.
        attempt_at = datetime.fromisoformat(write["at"].replace("Z", "+00:00"))
        self.assertLessEqual(datetime.fromisoformat(option["observed_at"].replace("Z", "+00:00")), attempt_at)
        self.assertLess(attempt_at, datetime.fromisoformat(option["expires_at"].replace("Z", "+00:00")))
        self.assertLess(attempt_at, datetime.fromisoformat(authority["expires_at"].replace("Z", "+00:00")))
        start = datetime.fromisoformat(option["starts_at"])
        self.assertEqual(start, datetime.fromisoformat(option["starts_at_utc"].replace("Z", "+00:00")))
        local = start.astimezone(ZoneInfo(option["timezone"]))
        self.assertEqual(local.isoformat(), option["starts_at"])
        self.assertEqual(local.replace(tzinfo=None).isoformat(), option["local_start"])

    def test_example_does_not_conflate_booking_calendar_reminder_or_delivery(self):
        booking = self.fixture["booking"]
        self.assertEqual(booking["authorization"]["allowed_effects"], ["provider_booking"])
        self.assertEqual(booking["provider_evidence"]["status"], "confirmed")
        self.assertIsNone(booking["calendar_event_id"])
        self.assertIsNone(booking["reminder_handoff"])
        self.assertEqual(booking["reply"]["state"], "pending")
        self.assertEqual(booking["cleanup"], {"owned_resources": [], "state": "verified"})

    def test_dst_examples_match_real_timezone_round_trips(self):
        for case in self.fixture["time_cases"]:
            with self.subTest(case=case["id"]):
                if case["timezone"] is None:
                    self.assertEqual(case["valid_instants"], [])
                    continue
                naive = datetime.fromisoformat(case["local_start"])
                zone = ZoneInfo(case["timezone"])
                instants = set()
                for fold in (0, 1):
                    local = naive.replace(tzinfo=zone, fold=fold)
                    utc = local.astimezone(timezone.utc)
                    if utc.astimezone(zone).replace(tzinfo=None) == naive:
                        instants.add(utc.isoformat().replace("+00:00", "Z"))
                self.assertEqual(sorted(instants), case["valid_instants"])


if __name__ == "__main__":
    unittest.main()
