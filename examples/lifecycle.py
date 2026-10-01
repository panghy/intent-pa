"""Single-owner, fake-transport reference model; NOT a live messaging bridge.

All times are UTC epoch seconds supplied by the caller. Keep the SQLite file in
private runtime storage, never in the pack checkout. Adapter names here are our
Python contract, not Intent or WhatsApp tool names. See docs/messaging.md.
"""

from dataclasses import asdict, dataclass
import json
import sqlite3


class Unknown(Exception):
    """A write may have succeeded, or a lookup cannot establish its outcome."""


class Unavailable(Exception):
    """A write is definitely unsent (never use this for a generic timeout)."""


@dataclass(frozen=True)
class Receipt:
    message_id: str
    state: str = "accepted"


def approval_valid(approval, sender, thread, version, now):
    """Version must identify the complete immutable action, including total."""
    return bool(
        approval and sender and thread and version
        and sender == approval.get("principal")
        and thread == approval.get("thread")
        and version == approval.get("version")
        and now < approval.get("expires_at", 0)
        and not approval.get("revoked", False)
    )


def needs_renewal(expires_at, now, active=True, margin=60):
    return active and (expires_at is None or expires_at <= now + margin)


class Lifecycle:
    """One process/owner at a time; SQLite persists transitions across restart.

    This model does not authenticate identities, enforce spending, create agents,
    drive hooks, compute local quiet hours, or guarantee exactly-once delivery.
    The caller supplies verified identities and quiet-hour policy decisions.
    """

    def __init__(self, path, principal="principal", thread="direct", channel=None):
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY, body TEXT)")
        row = self.db.execute("SELECT body FROM ledger WHERE id=1").fetchone()
        self.state = json.loads(row[0]) if row else {
            "principal": principal, "thread": thread, "channel": channel or "intent",
            "owner": None, "inbound": [], "outbox": {}, "progress": {},
            "reactions": {}, "corrections": {},
        }
        if row and (principal, thread, channel or "intent") != (
            self.state["principal"], self.state["thread"], self.state["channel"]
        ):
            self.db.close()
            raise ValueError("Use the persisted channel binding; migration needs reconciliation")
        self._save()

    def _save(self):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO ledger VALUES (1, ?)",
                            (json.dumps(self.state),))

    def close(self):
        self.db.close()

    def bind_owner(self, agent_id):
        """Persist a routing identity, not agent creation or a distributed lock."""
        if self.state["owner"] is None:
            self.state["owner"] = agent_id
            self._save()
        return self.state["owner"]

    def receive(self, sender, thread, message_id, now, own=False):
        if own or sender != self.state["principal"] or thread != self.state["thread"]:
            return False
        if message_id in self.state["inbound"]:
            return False
        self.state["inbound"].append(message_id)
        self._save()
        return True

    def enqueue(self, key, text, kind="final"):
        old = self.state["outbox"].get(key)
        if old:
            if (old["text"], old["kind"]) != (text, kind):
                raise ValueError("An outbox key cannot refer to a different message")
            return old
        item = {"text": text, "kind": kind, "state": "pending", "attempts": 0,
                "next_at": 0, "receipt": None, "escalated": False}
        self.state["outbox"][key] = item
        self._save()
        return item

    def _receipt(self, item, receipt):
        if not receipt.message_id or receipt.state not in {"accepted", "delivered", "read"}:
            raise Unknown("Unusable provider receipt")
        item["receipt"] = asdict(receipt)
        item["state"] = receipt.state
        self._save()

    def flush(self, adapter, now, quiet=False, current_versions=None):
        """One bounded pass. Return new outage notices for Ada's fallback channel.

        lookup(None) MUST mean authoritative absence. Raise Unknown when lookup
        is unsupported/inconclusive. An accepted receipt is not a read receipt.
        """
        notices = []
        for key, item in self.state["outbox"].items():
            if item["state"] in {"accepted", "delivered", "read", "failed"}:
                continue
            correction = self.state["corrections"].get(key)
            if item["kind"] == "correction" and correction is None:
                continue
            if correction and (current_versions or {}).get(correction["original"]) != correction["version"]:
                continue
            if quiet and item["kind"] in {"progress", "ack"}:
                continue
            if now < item["next_at"]:
                continue
            if item["state"] == "unknown":
                try:
                    receipt = adapter.lookup(key)
                    if receipt is not None:
                        self._receipt(item, receipt)
                        continue
                    item["state"] = "pending"
                except (Unknown, Unavailable, TimeoutError, OSError):
                    item["next_at"] = now + 60
                    if not item["escalated"]:
                        notices.append(f"Delivery unknown for {key}; reconcile before retrying.")
                        item["escalated"] = True
                    self._save()
                    continue
            if item["attempts"] >= 3:
                item["state"] = "failed"
                if not item["escalated"]:
                    notices.append(f"Delivery failed for {key}; final reply remains owed.")
                    item["escalated"] = True
                self._save()
                continue
            item["attempts"] += 1
            item["state"] = "unknown"
            item["next_at"] = now + 30 * (2 ** (item["attempts"] - 1))
            self._save()  # A crash after the send must enter reconciliation.
            try:
                self._receipt(item, adapter.send(key, item["text"]))
            except Unavailable:
                item["state"] = "pending"
                self._save()
            except (Unknown, TimeoutError, OSError):
                self._save()
        return notices

    def record_receipt(self, key, receipt):
        item = self.state["outbox"][key]
        previous = item["receipt"]
        if previous and previous["message_id"] != receipt.message_id:
            raise ValueError("Receipt belongs to another message")
        ranks = {"accepted": 0, "delivered": 1, "read": 2}
        if previous and ranks.get(receipt.state, -1) < ranks[previous["state"]]:
            return
        self._receipt(item, receipt)

    def acknowledge(self, message_id, adapter, now, verified=False):
        if message_id not in self.state["inbound"]:
            raise ValueError("Acknowledge only accepted incoming requests")
        emoji = "✅" if verified else "👀"
        old = self.state["reactions"].get(message_id)
        if old == emoji or (old == "✅" and not verified) or old == "unknown":
            return
        if "reaction" in adapter.capabilities:
            self.state["reactions"][message_id] = "unknown"
            self._save()
            try:
                adapter.react(message_id, emoji)  # Replace our reaction, do not add another.
            except Unavailable:
                self.state["reactions"].pop(message_id, None)
            except (Unknown, TimeoutError, OSError):
                return  # Reconcile reaction before a second acknowledgement.
            else:
                self.state["reactions"][message_id] = emoji
                self._save()
                return
        # Persist the chosen fallback with its outbox entry, including completion.
        self.state["reactions"][message_id] = emoji
        self.enqueue(f"ack:{message_id}:{emoji}",
                     "Completed and verified." if verified else "I’m working on this.", "ack")
        self._save()

    def progress(self, task, version, summary, now, quiet=False, verified=False):
        """Caller feeds passive snapshots; no worker messages or agent creation.

        First call starts the clock. Changes get a concise update after 30s;
        unchanged work permits one reminder after five minutes. Quiet time does
        not consume an update. Completion belongs in its own final outbox entry.
        """
        record = self.state["progress"].setdefault(task, {
            "started": now, "last_at": now, "last": None, "reminded": False,
        })
        if quiet or verified or now - record["started"] < 30:
            self._save()
            return None
        fingerprint = [version, summary]
        changed = fingerprint != record["last"]
        reminder = not changed and not record["reminded"] and now - record["last_at"] >= 300
        if not changed and not reminder:
            return None
        if now - record["last_at"] < 30:
            return None
        key = f"progress:{task}:{now}"
        record.update(last=fingerprint, last_at=now, reminded=record["reminded"] or reminder)
        self.enqueue(key, summary if changed else "I’m still working on this.", "progress")
        return key

    def correct(self, original_key, version, text, now):
        original = self.state["outbox"][original_key]
        if not original["receipt"]:
            raise ValueError("Reconcile the original assistant message first")
        key = f"correction:{original_key}:{version}"
        message_id = original["receipt"]["message_id"]
        self.state["corrections"].setdefault(key, {
            "original": original_key, "message_id": message_id, "version": version,
            "replacement": text, "created_at": now, "state": "prepared",
            "prior_text": original["text"],
        })
        self.enqueue(key, f"Correction to message {message_id}: {text}", "correction")
        self._save()
        return key

    def apply_correction(self, key, adapter, current_version):
        """Send/verify explicit correction first, then best-effort original repair.

        Only outbox-owned messages can be targets. Unknown edit/delete outcomes
        retain the delivered correction and require manual reconciliation.
        """
        record = self.state["corrections"][key]
        if record["version"] != current_version:
            raise ValueError("Stale correction; reconcile current task version")
        if record["state"] != "prepared":
            return record["state"]
        if self.state["outbox"][key]["state"] not in {"delivered", "read"}:
            return "awaiting-replacement"
        record["state"] = "repair-unknown"
        self._save()
        try:
            if "edit" in adapter.capabilities:
                adapter.edit(record["message_id"], record["replacement"])
                record["state"] = "edited"
            elif "delete_remote" in adapter.capabilities:
                adapter.delete(record["message_id"])
                record["state"] = "replaced"
            else:
                record["state"] = "linked-correction"
        except Unavailable:
            record["state"] = "linked-correction"
        except (Unknown, TimeoutError, OSError):
            record["state"] = "repair-unknown"
        self._save()
        return record["state"]
