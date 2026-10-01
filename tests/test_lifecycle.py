"""Functional tests of an offline reference model, never live connector coverage."""

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from examples.lifecycle import Lifecycle, Receipt, Unavailable, Unknown, approval_valid, needs_renewal


class FakeAdapter:
    def __init__(self, capabilities=(), sends=(), lookups=(), reaction_error=None, repair_error=None):
        self.capabilities = set(capabilities)
        self.sends = list(sends)
        self.lookups = list(lookups)
        self.reaction_error = reaction_error
        self.repair_error = repair_error
        self.calls = []

    @staticmethod
    def result(value):
        if isinstance(value, Exception):
            raise value
        return value

    def send(self, key, text):
        self.calls.append(("send", key, text))
        return self.result(self.sends.pop(0) if self.sends else Receipt(f"message-{key}"))

    def lookup(self, key):
        self.calls.append(("lookup", key))
        return self.result(self.lookups.pop(0) if self.lookups else Unknown("No authoritative lookup"))

    def react(self, message_id, emoji):
        self.calls.append(("react", message_id, emoji))
        self.result(self.reaction_error)

    def edit(self, message_id, text):
        self.calls.append(("edit", message_id, text))
        self.result(self.repair_error)

    def delete(self, message_id):
        self.calls.append(("delete", message_id))
        self.result(self.repair_error)


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "private.sqlite"
        self.model = Lifecycle(self.path)
        self.addCleanup(lambda: self.model.close())

    def restart(self, channel=None):
        self.model.close()
        self.model = Lifecycle(self.path, channel=channel)

    def crash_after_next_save(self):
        save = self.model._save

        def save_then_crash():
            save()
            raise SystemExit("Simulated abrupt process exit after durable save")

        return patch.object(self.model, "_save", side_effect=save_then_crash)

    def sent_original(self):
        self.model.enqueue("original", "The appointment is at 10.")
        self.model.flush(FakeAdapter(sends=[Receipt("original-id", "read")]), 0)

    def prepared_correction(self):
        self.sent_original()
        return self.model.correct("original", "v2", "The appointment is at 11.", 10)

    def delivered_correction(self):
        key = self.prepared_correction()
        self.model.flush(FakeAdapter(sends=[Receipt("correction-id", "delivered")]), 10,
                         current_versions={"original": "v2"})
        return key

    def test_optional_channel_uses_intent_and_retains_single_owner(self):
        self.assertEqual(self.model.state["channel"], "intent")
        self.assertEqual(self.model.bind_owner("ada-session"), "ada-session")
        self.restart()
        self.assertEqual(self.model.bind_owner("another-session"), "ada-session")

    def test_configured_channel_survives_outage_and_restart(self):
        self.model.close()
        self.path.unlink()
        self.model = Lifecycle(self.path, channel="whatsapp")
        self.model.enqueue("final", "The draft is ready.")
        self.model.flush(FakeAdapter(sends=[Unavailable()]), 0)
        self.restart(channel="whatsapp")
        self.assertEqual(self.model.state["channel"], "whatsapp")
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "pending")
        with self.assertRaisesRegex(ValueError, "persisted channel"):
            Lifecycle(self.path)

    def test_inbound_replay_sender_thread_and_own_echo_are_rejected(self):
        self.assertTrue(self.model.receive("principal", "direct", "request", 0))
        self.restart()
        for sender, thread, identifier, own in (
            ("principal", "direct", "request", False),
            ("vendor", "direct", "injection", False),
            ("principal", "group", "group-request", False),
            ("principal", "direct", "echo", True),
        ):
            self.assertFalse(self.model.receive(sender, thread, identifier, 30, own=own))
        self.assertEqual(self.model.state["inbound"], ["request"])

    def test_pending_final_reply_is_durable_and_sent_once(self):
        self.model.enqueue("final", "Done and verified.")
        self.restart()
        adapter = FakeAdapter()
        self.model.flush(adapter, 30)
        self.model.enqueue("final", "Done and verified.")
        self.model.flush(adapter, 60)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "accepted")
        with self.assertRaises(ValueError):
            self.model.enqueue("final", "A different claim.")

    def test_timeout_then_restart_reconciles_without_second_send(self):
        adapter = FakeAdapter(sends=[TimeoutError()], lookups=[Receipt("provider-id", "delivered")])
        self.model.enqueue("final", "Ready.")
        self.model.flush(adapter, 0)
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "unknown")
        self.restart()
        self.model.flush(adapter, 30)
        self.assertEqual([c[0] for c in adapter.calls], ["send", "lookup"])
        self.assertEqual(self.model.state["outbox"]["final"]["receipt"]["message_id"], "provider-id")

    def test_crash_after_pre_send_save_reconciles_before_first_actual_send(self):
        self.model.enqueue("final", "Ready.")
        adapter = FakeAdapter(lookups=[None])
        with self.crash_after_next_save(), self.assertRaises(SystemExit):
            self.model.flush(adapter, 0)
        self.assertEqual(adapter.calls, [])
        self.restart()
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "unknown")
        self.model.flush(adapter, 30)
        self.assertEqual([call[0] for call in adapter.calls], ["lookup", "send"])

    def test_unknown_outcome_never_retries_blindly(self):
        adapter = FakeAdapter(sends=[Unknown()])
        self.model.enqueue("final", "Ready.")
        self.model.flush(adapter, 0)
        self.assertEqual(len(self.model.flush(adapter, 30)), 1)
        self.assertEqual(self.model.flush(adapter, 90), [])
        self.assertEqual(sum(c[0] == "send" for c in adapter.calls), 1)
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "unknown")

    def test_authoritative_absence_allows_retry(self):
        adapter = FakeAdapter(sends=[Unknown(), Receipt("retry-id")], lookups=[None])
        self.model.enqueue("final", "Ready.")
        self.model.flush(adapter, 0)
        self.model.flush(adapter, 30)
        self.assertEqual([c[0] for c in adapter.calls], ["send", "lookup", "send"])
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "accepted")

    def test_known_unsent_retries_back_off_and_escalate_once(self):
        adapter = FakeAdapter(sends=[Unavailable(), Unavailable(), Unavailable()])
        self.model.enqueue("final", "Ready.")
        for now in (0, 29, 30, 89, 90, 209):
            self.model.flush(adapter, now)
        self.assertEqual(len(adapter.calls), 3)
        notices = self.model.flush(adapter, 210)
        self.assertEqual(len(notices), 1)
        self.assertIn("reply remains owed", notices[0])
        self.assertEqual(self.model.flush(adapter, 999), [])
        self.assertEqual(self.model.state["outbox"]["final"]["kind"], "final")

    def test_sent_delivered_and_read_are_distinct_monotonic_receipts(self):
        self.model.enqueue("final", "Ready.")
        self.model.flush(FakeAdapter(), 0)
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "accepted")
        self.model.record_receipt("final", Receipt("message-final", "delivered"))
        self.model.record_receipt("final", Receipt("message-final", "read"))
        self.model.record_receipt("final", Receipt("message-final", "accepted"))
        self.assertEqual(self.model.state["outbox"]["final"]["state"], "read")
        with self.assertRaises(ValueError):
            self.model.record_receipt("final", Receipt("someone-elses-message", "read"))

    def test_reactions_acknowledge_once_then_complete_only_on_verification(self):
        adapter = FakeAdapter(capabilities={"reaction"})
        self.model.receive("principal", "direct", "request", 0)
        self.model.acknowledge("request", adapter, 0)
        self.model.acknowledge("request", adapter, 30)
        self.model.enqueue("final", "Work queued.")
        self.assertEqual(adapter.calls, [("react", "request", "👀")])
        self.model.acknowledge("request", adapter, 60, verified=True)
        self.model.acknowledge("request", adapter, 90)
        self.assertEqual(adapter.calls[-1], ("react", "request", "✅"))
        self.assertEqual(len(adapter.calls), 2)

    def test_missing_or_failed_reaction_falls_back_to_one_acknowledgement(self):
        for capabilities, error in ((set(), None), ({"reaction"}, Unavailable())):
            with self.subTest(capabilities=capabilities):
                identifier = "request-" + str(bool(capabilities))
                adapter = FakeAdapter(capabilities=capabilities, reaction_error=error)
                self.model.receive("principal", "direct", identifier, 0)
                self.model.acknowledge(identifier, adapter, 0)
                self.model.acknowledge(identifier, adapter, 30)
                matches = [k for k in self.model.state["outbox"] if k.startswith(f"ack:{identifier}:")]
                self.assertEqual(len(matches), 1)

    def test_unknown_reaction_does_not_create_duplicate_ack(self):
        adapter = FakeAdapter(capabilities={"reaction"}, reaction_error=TimeoutError())
        self.model.receive("principal", "direct", "request", 0)
        self.model.acknowledge("request", adapter, 0)
        self.restart()
        self.model.acknowledge("request", adapter, 30)
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(self.model.state["outbox"], {})

    def check_crash_after_fallback_enqueue(self, verified):
        for capabilities in (set(), {"reaction"}):
            with self.subTest(capabilities=capabilities):
                identifier = "request-" + str(bool(capabilities))
                emoji = "✅" if verified else "👀"
                key = f"ack:{identifier}:{emoji}"
                self.model.receive("principal", "direct", identifier, 0)
                if verified:
                    self.model.acknowledge(identifier, FakeAdapter({"reaction"}), 0)
                    self.model.enqueue(f"final:{identifier}", "The result is ready.")
                unavailable = FakeAdapter(capabilities, reaction_error=Unavailable())
                save = self.model._save

                def save_then_crash_on_fallback():
                    save()
                    if key in self.model.state["outbox"]:
                        raise SystemExit("Crash after fallback acknowledgement persisted")

                with patch.object(self.model, "_save", side_effect=save_then_crash_on_fallback):
                    with self.assertRaises(SystemExit):
                        self.model.acknowledge(identifier, unavailable, 10, verified=verified)
                self.restart()
                recovered = FakeAdapter({"reaction"})
                self.model.acknowledge(identifier, recovered, 30, verified=verified)
                self.model.acknowledge(identifier, recovered, 30)
                self.model.flush(recovered, 30, quiet=True)
                self.assertEqual(self.model.state["outbox"][key]["state"], "pending")
                if verified:
                    self.assertEqual(self.model.state["outbox"][f"final:{identifier}"]["state"],
                                     "accepted")
                self.model.flush(recovered, 60)
                self.restart()
                self.model.acknowledge(identifier, recovered, 90, verified=verified)
                self.model.flush(recovered, 90)
                expected = [("send", f"final:{identifier}", "The result is ready.")] if verified else []
                expected.append(("send", key,
                                 "Completed and verified." if verified else "I’m working on this."))
                self.assertEqual(recovered.calls, expected)
                self.assertEqual(self.model.state["reactions"][identifier], emoji)
                self.assertEqual(self.model.state["outbox"][key]["state"], "accepted")

    def test_crash_after_working_fallback_enqueue_does_not_duplicate_ack(self):
        self.check_crash_after_fallback_enqueue(verified=False)

    def test_crash_after_completion_fallback_enqueue_preserves_final_delivery(self):
        self.check_crash_after_fallback_enqueue(verified=True)

    def test_progress_at_30_seconds_then_only_change_or_one_bounded_reminder(self):
        for now in (0, 29):
            self.assertIsNone(self.model.progress("task", "v1", "Checking availability.", now))
        self.assertIsNotNone(self.model.progress("task", "v1", "Checking availability.", 30))
        self.assertIsNone(self.model.progress("task", "v1", "Checking availability.", 60))
        self.assertIsNotNone(self.model.progress("task", "v1", "Comparing two options.", 90))
        self.assertIsNotNone(self.model.progress("task", "v1", "Comparing two options.", 390))
        self.assertIsNone(self.model.progress("task", "v1", "Comparing two options.", 990))

    def test_crash_after_progress_enqueue_preserves_deduplication_state(self):
        self.model.progress("task", "v1", "Checking availability.", 0)
        with self.crash_after_next_save(), self.assertRaises(SystemExit):
            self.model.progress("task", "v1", "Checking availability.", 30)
        self.restart()
        self.assertEqual(len(self.model.state["outbox"]), 1)
        self.assertIsNone(self.model.progress("task", "v1", "Checking availability.", 60))
        self.assertEqual(len(self.model.state["outbox"]), 1)

    def test_quiet_hours_do_not_consume_progress_and_completion_suppresses_it(self):
        self.model.progress("task", "v1", "Checking.", 0)
        self.assertIsNone(self.model.progress("task", "v1", "Checking.", 30, quiet=True))
        self.assertEqual(self.model.state["outbox"], {})
        key = self.model.progress("task", "v1", "Checking.", 60)
        adapter = FakeAdapter()
        self.model.flush(adapter, 60, quiet=True)
        self.assertEqual(adapter.calls, [])
        self.model.flush(adapter, 90)
        self.assertEqual(adapter.calls[0][1], key)
        self.assertIsNone(self.model.progress("task", "v1", "Ready.", 120, verified=True))

    def test_correction_cannot_target_user_or_unreconciled_message(self):
        with self.assertRaises(KeyError):
            self.model.correct("user-message", "v2", "Change user text", 0)
        self.model.enqueue("unsent", "Not sent yet.")
        with self.assertRaisesRegex(ValueError, "Reconcile"):
            self.model.correct("unsent", "v2", "New claim", 0)

    def test_correction_without_version_and_audit_metadata_never_flushes(self):
        self.model.enqueue("orphan-correction", "An incomplete correction.", kind="correction")
        self.restart()
        adapter = FakeAdapter()
        self.model.flush(adapter, 30)
        self.assertEqual(adapter.calls, [])
        self.assertEqual(self.model.state["outbox"]["orphan-correction"]["state"], "pending")

    def test_correction_prepared_before_send_and_no_deletion_during_failure(self):
        key = self.prepared_correction()
        adapter = FakeAdapter(capabilities={"delete_remote"}, sends=[Unavailable()])
        self.model.flush(adapter, 10, current_versions={"original": "v2"})
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "awaiting-replacement")
        self.assertFalse(any(c[0] == "delete" for c in adapter.calls))
        self.assertIn("Correction to message original-id", self.model.state["outbox"][key]["text"])
        self.assertEqual(self.model.state["corrections"][key]["prior_text"], "The appointment is at 10.")

    def test_stale_correction_neither_sends_nor_repairs(self):
        key = self.prepared_correction()
        adapter = FakeAdapter(capabilities={"edit"})
        self.model.flush(adapter, 10, current_versions={"original": "v3"})
        self.assertEqual(adapter.calls, [])
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.model.apply_correction(key, adapter, "v3")

    def test_crash_after_correction_enqueue_preserves_version_guard_and_audit(self):
        self.sent_original()
        with self.crash_after_next_save(), self.assertRaises(SystemExit):
            self.model.correct("original", "v2", "The appointment is at 11.", 10)
        self.restart()
        key = "correction:original:v2"
        self.assertIn(key, self.model.state["outbox"])
        self.assertEqual(self.model.state["corrections"][key]["version"], "v2")
        self.assertEqual(self.model.state["corrections"][key]["prior_text"], "The appointment is at 10.")
        adapter = FakeAdapter()
        self.model.flush(adapter, 40, current_versions={"original": "v3"})
        self.assertEqual(adapter.calls, [])
        self.model.flush(adapter, 70, current_versions={"original": "v2"})
        self.assertEqual(len(adapter.calls), 1)

    def test_verified_replacement_allows_edit_and_records_private_trail(self):
        key = self.delivered_correction()
        adapter = FakeAdapter(capabilities={"edit", "delete_remote"})
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "edited")
        self.assertEqual(adapter.calls, [("edit", "original-id", "The appointment is at 11.")])
        self.restart()
        self.model.apply_correction(key, adapter, "v2")
        self.assertEqual(len(adapter.calls), 1)
        self.assertEqual(self.model.state["corrections"][key]["prior_text"], "The appointment is at 10.")

    def test_delete_only_after_verified_replacement(self):
        key = self.delivered_correction()
        adapter = FakeAdapter(capabilities={"delete_remote"})
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "replaced")
        self.assertEqual(adapter.calls, [("delete", "original-id")])

    def test_unsupported_local_only_or_failed_removal_keeps_linked_correction(self):
        key = self.delivered_correction()
        adapter = FakeAdapter(capabilities={"delete_local"})
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "linked-correction")
        self.assertEqual(adapter.calls, [])

    def test_failed_delete_retains_delivered_linked_correction(self):
        key = self.delivered_correction()
        adapter = FakeAdapter(capabilities={"delete_remote"}, repair_error=Unavailable("Too late"))
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "linked-correction")
        self.assertEqual(self.model.state["outbox"][key]["state"], "delivered")

    def test_unknown_replacement_reconciles_before_removing_original(self):
        key = self.prepared_correction()
        adapter = FakeAdapter(capabilities={"delete_remote"}, sends=[Unknown()],
                              lookups=[Receipt("replacement-id", "delivered")])
        self.model.flush(adapter, 10, current_versions={"original": "v2"})
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "awaiting-replacement")
        self.restart()
        self.model.flush(adapter, 40, current_versions={"original": "v2"})
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "replaced")
        self.assertEqual([c[0] for c in adapter.calls], ["send", "lookup", "delete"])

    def test_unknown_edit_is_not_repeated_blindly(self):
        key = self.delivered_correction()
        adapter = FakeAdapter(capabilities={"edit"}, repair_error=Unknown())
        self.assertEqual(self.model.apply_correction(key, adapter, "v2"), "repair-unknown")
        self.restart()
        self.model.apply_correction(key, adapter, "v2")
        self.assertEqual(len(adapter.calls), 1)

    def test_approval_is_bound_to_identity_thread_action_version_expiry_and_revocation(self):
        approval = dict(principal="principal", thread="direct", version="v2-total-50", expires_at=60)
        self.assertTrue(approval_valid(approval, "principal", "direct", "v2-total-50", 30))
        for sender, thread, version, now in (
            ("vendor", "direct", "v2-total-50", 30),
            ("principal", "group", "v2-total-50", 30),
            ("principal", "direct", "v3-total-80", 30),
            ("principal", "direct", "v2-total-50", 60),
        ):
            self.assertFalse(approval_valid(approval, sender, thread, version, now))
        approval["revoked"] = True
        self.assertFalse(approval_valid(approval, "principal", "direct", "v2-total-50", 30))
        self.assertFalse(approval_valid(None, "principal", "direct", "v2-total-50", 30))

    def test_schedule_renewal_before_expiry_after_downtime_and_only_while_active(self):
        self.assertFalse(needs_renewal(120, 0))
        self.assertTrue(needs_renewal(120, 60))
        self.assertTrue(needs_renewal(120, 180))
        self.assertTrue(needs_renewal(None, 0))
        self.assertFalse(needs_renewal(120, 180, active=False))


if __name__ == "__main__":
    unittest.main()
