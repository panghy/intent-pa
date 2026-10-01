import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_pack import BOOKING_ROLES, EXPECTED_IDS, load_procedures, load_sources, parse_generated, render, validate
from check_intent_parser import function


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / "source", self.root / "source")
        shutil.copytree(ROOT / "specialists", self.root / "specialists")

    def config(self, change):
        path = self.root / "source/pack.json"
        config = json.loads(path.read_text())
        change(config)
        path.write_text(json.dumps(config))

    def test_reproducible_generated_pack(self):
        self.assertEqual(validate(self.root), 11)
        self.assertEqual(render(self.root), render(self.root))
        self.assertEqual(set(render(self.root)), {f"{i}.md" for i in EXPECTED_IDS})

    def test_every_loaded_body_includes_identical_complete_charter(self):
        version, _, charter = load_sources(self.root)
        for filename, content in render(self.root).items():
            with self.subTest(filename=filename):
                metadata, body = parse_generated(content)
                self.assertIn(f"Charter version: {version}", body)
                self.assertEqual(body.count(charter), 1)
                self.assertTrue(metadata["roleReminder"])

    def test_booking_procedure_is_complete_and_only_in_booking_roles(self):
        procedure = load_procedures(self.root)["appointment-booking"]["body"]
        for filename, content in render(self.root).items():
            with self.subTest(filename=filename):
                _, body = parse_generated(content)
                self.assertEqual(body.count(procedure), int(Path(filename).stem in BOOKING_ROLES))

    def test_missing_procedure_registration_is_rejected(self):
        self.config(lambda c: c.pop("procedures"))
        with self.assertRaisesRegex(ValueError, "Expected the appointment-booking"):
            render(self.root)

    def test_missing_or_duplicate_procedure_consumers_are_rejected(self):
        for consumers in (["pa-ada"], ["pa-ada", "pa-tempo", "pa-tempo"],
                          ["pa-ada", "pa-tempo", "pa-scout"], "pa-ada"):
            with self.subTest(consumers=consumers):
                self.config(lambda c: c["procedures"]["appointment-booking"].update(specialists=consumers))
                with self.assertRaisesRegex(ValueError, "Ada, Tempo and Auditor"):
                    render(self.root)

    def test_invalid_procedure_version_is_rejected(self):
        for version in ("1.0", "latest", 1, None):
            with self.subTest(version=version):
                self.config(lambda c: c["procedures"]["appointment-booking"].update(version=version))
                with self.assertRaisesRegex(ValueError, "semantic version"):
                    render(self.root)

    def test_empty_or_missing_procedure_fails_build(self):
        path = self.root / "source/procedures/appointment-booking.md"
        path.write_text(" \n")
        with self.assertRaisesRegex(ValueError, "Empty procedure"):
            render(self.root)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            render(self.root)

    def test_procedure_changes_and_version_bumps_require_regeneration(self):
        path = self.root / "source/procedures/appointment-booking.md"
        original = path.read_text()
        path.write_text(original + "\nA changed booking step.\n")
        with self.assertRaisesRegex(ValueError, "differs from source"):
            validate(self.root)
        path.write_text(original)
        self.config(lambda c: c["procedures"]["appointment-booking"].update(version="1.0.1"))
        with self.assertRaisesRegex(ValueError, "differs from source"):
            validate(self.root)

    def test_removed_procedure_in_any_consumer_is_rejected(self):
        procedure = load_procedures(self.root)["appointment-booking"]["body"]
        for identifier in BOOKING_ROLES:
            with self.subTest(identifier=identifier):
                path = self.root / "specialists" / f"{identifier}.md"
                original = path.read_text()
                path.write_text(original.replace(procedure, ""))
                with self.assertRaisesRegex(ValueError, identifier):
                    validate(self.root)
                path.write_text(original)

    def test_ada_roster_resolves_all_workers_once(self):
        metadata, _ = parse_generated(render(self.root)["pa-ada.md"])
        self.assertEqual(metadata["role"], "orchestrator")
        self.assertEqual(len(metadata["teamAgents"]), 10)
        self.assertEqual(set(metadata["teamAgents"]), EXPECTED_IDS - {"pa-ada"})
        for identifier in metadata["teamAgents"]:
            worker, _ = parse_generated(render(self.root)[f"{identifier}.md"])
            self.assertEqual(worker["role"], "internal")
            self.assertNotIn("teamAgents", worker)

    def test_missing_charter_in_one_artifact_is_rejected(self):
        path = self.root / "specialists/pa-tempo.md"
        _, _, charter = load_sources(self.root)
        path.write_text(path.read_text().replace(charter, ""))
        with self.assertRaisesRegex(ValueError, "pa-tempo.md"):
            validate(self.root)

    def test_stale_artifact_after_charter_change_is_rejected(self):
        path = self.root / "source/charter.md"
        path.write_text(path.read_text() + "\nA revised shared obligation.\n")
        with self.assertRaisesRegex(ValueError, "differs from source"):
            validate(self.root)

    def test_duplicate_id_is_rejected(self):
        self.config(lambda c: c["specialists"][1].update(id="pa-ada"))
        with self.assertRaisesRegex(ValueError, "eleven unique"):
            render(self.root)

    def test_missing_role_is_rejected(self):
        self.config(lambda c: c["specialists"].pop())
        with self.assertRaisesRegex(ValueError, "eleven unique"):
            render(self.root)

    def test_unknown_metadata_is_rejected(self):
        self.config(lambda c: c["specialists"][0].update(permissions="all"))
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            render(self.root)

    def test_worker_cannot_gain_orchestrator_role(self):
        self.config(lambda c: c["specialists"][1].update(role="orchestrator"))
        with self.assertRaisesRegex(ValueError, "Invalid role"):
            render(self.root)

    def test_missing_and_extra_artifacts_are_rejected(self):
        path = self.root / "specialists/pa-tempo.md"
        path.unlink()
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate(self.root)
        path.write_text(render(self.root)[path.name])
        (path.parent / "common.md").write_text("This must not load as another specialist")
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate(self.root)

    def test_frontmatter_remains_single_line_supported_json_subset(self):
        self.config(lambda c: c["specialists"][0].update(name='Ada: "Chief"\nSecond line'))
        metadata, _ = parse_generated(render(self.root)["pa-ada.md"])
        self.assertEqual(metadata["name"], 'Ada: "Chief"\nSecond line')

    def test_parser_extraction_fails_if_upstream_contract_changes(self):
        with self.assertRaisesRegex(ValueError, "review upstream"):
            function("fn renamed() {}", "parse_frontmatter")

    def test_private_store_contract_survives_specialists_only_install(self):
        # Installation has no source/docs includes: inspect the actual shipped bodies.
        required = (
            "dedicated private operational store",
            "Steward is the single integration owner",
            "Persist a handoff before notifying its recipient",
            "expected base and record versions",
            "acknowledge only after reading and validating",
            "Never use last-writer-wins for authority or conflicting facts",
            "confirm the remote ref before calling a checkpoint synced",
            "Git restore never authorizes replay",
            "No routine user review of branches, commits or PRs",
            "Actual tool restrictions and higher-priority rules still apply",
        )
        for path in sorted((self.root / "specialists").glob("*.md")):
            _, body = parse_generated(path.read_text())
            for obligation in required:
                with self.subTest(role=path.stem, obligation=obligation):
                    self.assertIn(obligation, body)
            self.assertNotIn("No credentials or personal records in a Git repository", body)

    def test_git_contract_removal_from_any_installed_role_is_detected(self):
        for path in sorted((self.root / "specialists").glob("*.md")):
            with self.subTest(role=path.stem):
                original = path.read_text()
                start = original.index("### Internal Git collaboration")
                end = original.index("### Recovery and cleanup", start)
                path.write_text(original[:start] + original[end:])
                with self.assertRaisesRegex(ValueError, path.name):
                    validate(self.root)
                path.write_text(original)

    def test_store_owners_are_installed_with_their_specific_responsibilities(self):
        owners = {
            "pa-ada": "substantive personal decisions",
            "pa-keeper": "field authority and record versions",
            "pa-steward": "restore verification",
            "pa-auditor": "consequential record and schema changes",
        }
        for role, responsibility in owners.items():
            _, body = parse_generated((self.root / "specialists" / (role + ".md")).read_text())
            role_body = body.split("# " + role[3:].capitalize() + " —", 1)[1]
            with self.subTest(role=role):
                self.assertIn(responsibility, role_body)

    def test_approved_messaging_rules_reach_every_prompt(self):
        obligations = (
            "approximately 30-second passive progress/delivery watchdog",
            "must not send interrupting status probes",
            "current human-facing Intent conversation is the interface",
            "✅ means verified task completion",
            "Track task completion and final reply delivery separately",
            "Reconcile unknown replacement sends",
            "Never erase user/vendor messages",
            "Renew still-authorized schedules before hook expiration",
            "Silence is never approval",
            "Never store secrets or raw account exports in Git",
            "success, failure and cancellation paths",
        )
        for filename, content in render(self.root).items():
            _, body = parse_generated(content)
            for obligation in obligations:
                with self.subTest(filename=filename, obligation=obligation):
                    self.assertIn(obligation, body)


if __name__ == "__main__":
    unittest.main()
