# Messaging capability and adapter contract

The selected reply owner’s current human-facing Intent conversation is the default interface. Missing
WhatsApp is not a setup failure. If the user selects an external channel, persist
its account, verified principal and direct thread and use it for user-visible
replies. A configured channel outage is different from an unconfigured channel:
preserve its pending replies and explain the outage through an already reachable,
authorized fallback, rather than silently changing the binding.

No particular WhatsApp connector is included or assumed. Inspect real tool schemas
at startup and after reconnect, as shown in [installation](installation.md).
Record capability evidence and its verification date in private runtime notes.

## Capability checks

| Capability | Verify with the actual connector | If missing |
| --- | --- | --- |
| Account and identity | Stable account, authenticated sender and direct thread identifiers; group and own-message flags | Do not route unverified input as principal instructions |
| Incoming wakeup | Durable webhook/event subscription or bounded polling with cursor, replay and gap detection; idle daemon can wake Ada | A read/send tool is insufficient; implement a bridge or remain in Intent |
| Send and idempotency | Stable request key, provider message ID, exact meaning of timeout and rejection | Keep outcome unknown after ambiguous writes; never blind-retry |
| Reconciliation | Lookup by request/message ID, authoritative absence versus eventual-consistency lag | Hold uncertain sends and escalate; no exactly-once claim |
| Receipts | Distinct accepted, sent, delivered and read states, including unsupported states | Report only the state actually observed |
| Reactions | Set/replace/remove the assistant's own reaction, target inbound ID, limits and read-back | Short acknowledgement in the outbox; no duplicate ack |
| Edit own message | Ownership, time window, remote visibility, post-edit read-back | Explicit linked correction |
| Delete own message | Remote deletion versus local-only hiding, ownership, time window and result read-back | Keep original and post linked correction |
| Attachments | Types, size, malware handling and retention | Ask for supported content through the selected channel |
| Reconnect/revocation | Credential expiry, account change, revoked scopes and resume cursor | Pause affected operations and use the secure reconnection flow |

A connector supplies only the guarantees it documents and demonstrates. The
adapter/runtime must supply routing leases, durable inbound and outbox storage,
authorization enforcement, action ownership, retry policy and schedule recovery.
Specialist prompts, `role`, `teamAgents` and an Auditor review are not security
boundaries. If tool or broker enforcement is absent, describe the deployment as
a supervised prototype, not an autonomous assistant with enforced spending limits.

## Inbound routing and approvals

Persist `(account, thread, provider_message_id)` before acknowledging or creating
work. Authenticate the principal at the transport boundary. Reject unknown senders,
groups and assistant-originated events from the user-instruction route; vendor
responses become evidence on an existing task. Advance the receive cursor only
after durable acceptance. Replaying input must reuse the existing task and Ada
identity. Serialize bootstrap/agent creation and reconcile timeouts so two receivers
cannot create two conversation owners.

An action approval binds to a complete immutable version: recipient/account,
item/date, amount including tax/fees, currency, scope and expiry. A material change
invalidates approval. Revocation is checked at execution time. A bare “yes” is valid
only for one unambiguous pending proposal in the authenticated principal's thread.
Unknown senders, stale versions and forwarded/vendor approvals cannot authorize an
action. Keep routine approval and clarification usable in the selected conversation
or a supported secure link; do not depend on a desktop-only approval card.

The reference `approval_valid` checks identity/thread/version/expiry/revocation
fields after authentication. It does not interpret “yes,” enforce monetary limits
or perform the external action. Those belong in the live action broker.

## Acknowledgement, progress and completion

Use one supported reaction such as 👀 to the inbound request while working. Replace
or remove only the assistant's own reaction when state changes; ✅ requires a
verified outcome, not a queued task or accepted send. With no reaction support,
queue a brief acknowledgement. An ambiguous reaction write needs reconciliation
before retry or a text fallback, which could otherwise duplicate the acknowledgement.

Prefer worker completion events. While work is active, use a consolidated passive
check about every 30 seconds to read worker status, task notes and, when necessary,
recent conversation. Never send a status-probing message to the worker; it can
interrupt work. The recorded owner remains the only sender for that request: Ada for ongoing work, direct Pip for its brief exchange. The first check can
produce a useful short update if the user has had no feedback. Later checks send
only meaningful changes or a bounded still-working reminder. Suppress unchanged
chatter and apply the principal's timezone/quiet hours and agreed urgent exceptions.

Work completion and final reply delivery are separate obligations. Persist a
versioned final reply before attempting transport. Keep stable outbox keys across
restart and retries; do not overwrite a queued payload under an old key. Record
provider IDs and accurate receipt states. An accepted send is not confirmed delivery
and delivery is not evidence that the user read it.

On an ambiguous timeout, record `unknown`, query the provider, then retry only
after authoritative absence or a verified provider idempotency guarantee. A
production bridge should use provider idempotency as an extra defense. An eventual
search miss is not authoritative absence. Retry definite failures with bounded
backoff; after exhaustion retain the final-reply obligation and alert Ada. Explain
an outage in the current reachable conversation if available, without claiming the
unavailable channel delivered anything. If there is no reachable channel, preserve
the backlog and alert the operator when possible. Never promise guaranteed delivery
during a service outage.

## Correcting an assistant message

Reconcile the original provider ID, ownership and current task version. Prepare
the accurate replacement and preserve a private audit trail of old text, new text,
reason, action version and transport outcomes. When the original could have been
read or acted on, always send an explicit linked correction even if editing works.
Do not delete user/vendor messages or imply a chat edit reverses a booking/payment.

The reference takes the conservative path: queue an explicit correction, verify
that replacement was delivered/read, then edit the original if supported or delete
the original remotely if supported. If removal is unsupported, too late, local-only
or fails, the already delivered linked correction is the fallback. If the replacement
send fails or its delivery cannot be established, leave the original visible and
retain the correction obligation. Do not remove the only answer first. An ambiguous
edit/delete requires read-back; do not blindly perform the other operation.

## Offline reference API

[`examples/lifecycle.py`](../examples/lifecycle.py) uses Python's standard library
and a SQLite ledger. All timestamps are UTC epoch **seconds** supplied by the caller.
It is single-owner and fake-transport only; use private temporary storage in tests.
[`examples/demo.py`](../examples/demo.py) demonstrates an accepted send whose
response is lost, followed by restart and lookup without a duplicate send.

These Python adapter names are **local contracts**, not real MCP tool names:

| Adapter operation | Contract |
| --- | --- |
| `capabilities` | Set containing verified `reaction`, `edit`, `delete_remote` flags |
| `send(key, text)` | Return `Receipt(message_id, state)`; stable key is retained by caller |
| `lookup(key)` | Return receipt, `None` only for authoritative absence, or raise `Unknown` |
| `react(message_id, emoji)` | Replace the assistant's own reaction; return only on verified success |
| `edit(message_id, text)` | Edit assistant-owned original; adapter verifies remote result |
| `delete(message_id)` | Remote deletion of assistant-owned original; adapter verifies result |

`Unavailable` means definitely unsent, not a generic network failure. `Unknown`,
`TimeoutError` and `OSError` mean possible success. A real adapter must map its
provider's errors conservatively. Unsupported/inconclusive lookup must raise
`Unknown`; returning `None` would authorize a potentially duplicate send.

`Lifecycle(path, principal, thread, channel)` persists the selected binding and
refuses accidental rebinding after restart. With `channel=None` it records `intent`;
that models routing selection and does not post into a live Intent conversation.
`receive` deduplicates trusted inbound IDs, `bind_owner` retains one existing
identity, and `enqueue`/`flush` model outbox transitions. Three send attempts use
30/60/120-second backoff. An unknown outcome is reconciled before another send;
inconclusive reconciliation emits one outage notice and continues at a slow cadence.
The returned notices are obligations for Ada; the example does not transmit them.

`record_receipt` monotonically advances a matching provider ID from accepted to
delivered/read. `progress` accepts passive snapshots; call once when the task starts,
then at each check. It queues a first update after 30 seconds, meaningful changes
thereafter, and at most one unchanged reminder after five minutes. It does not
create workers or final replies. `flush(..., quiet=True)` holds progress and
acknowledgements; the caller decides whether final replies/corrections are urgent
under the user's policy and whether to call `flush` during quiet hours at all.

`correct(original_key, version, text, now)` prepares the replacement. Before sending,
pass `flush(..., current_versions={original_key: version})`; a missing or stale
version holds the correction. After receipt confirmation,
`apply_correction(key, adapter, current_version)` verifies version again before
editing/deleting. Only previously reconciled outbox messages can be correction
targets. Unsupported removal yields `linked-correction`; ambiguous removal yields
`repair-unknown`. The original/replacement trail stays in the private ledger.

### Explicit limits

The example is not a production database or concurrent queue: one caller owns its
whole ledger. It has no webhook receiver, process supervisor, authentication,
distributed lease, agent creation, encryption/retention manager, real connector,
local-time policy engine or general action broker. Reaction reconciliation and
ambiguous repair read-back are deliberately handed to the operator/adapter;
the model suppresses repeated writes. Delivery polling after an accepted receipt
is the adapter's responsibility through `record_receipt`. Failed messages require
an explicit operator recovery decision, not infinite automatic retries. Watch
renewal is a predicate/example workflow, not an installed scheduler. Passing
offline tests proves the modeled transitions only.


Pip does not implicitly replace an external channel's durable Ada binding. For a
Pip-owned request, serialize accepted transfer of that request's reply/outbox and
worker-result obligations as described in [operations](operations.md#brief-chat-and-durable-handoff).
An internal Pip call never sends a second channel reply. Pending transfers remain
recoverable and are reported as blocked when no durable owner accepts them.
