# Progress, delivery and recovery

Keep a private task/action ledger, channel binding, outbox, schedule ledger and
resource registry. Store IDs and compact facts with provenance; keep credentials
in the credential service and original documents in their authoritative systems.
Ada owns user replies; workers return evidence and cleanup status to Ada.

## Passive progress and delivery watchdog

[`examples/watchdog.mjs`](../examples/watchdog.mjs) exports a concrete
`scheduleWatchdog(ws, ledgerNoteId)` function. It uses the verified Intent APIs
`ws.hook.schedule`, `ws.agent.status` and `ws.note.read`. Importing it does nothing.
Copy its function into a `workspace_api` call in Ada's session and invoke it only
after creating the private ledger note below. It is an example for an authorized
active task, not an automatically installed hook.

The note's `rawContent` must be JSON, without Markdown fences. Replace the example
IDs with actual worker/task note IDs; timestamps here use UTC epoch **milliseconds**:

```json
{
  "active": true,
  "workers": [{"agentId": "WORKER_AGENT_ID", "noteId": "TASK_NOTE_ID"}],
  "outboxRevision": 0,
  "delivery": null,
  "quietUntil": 0,
  "lastUserFeedbackAt": 0,
  "renewAt": 0
}
```

Ada updates `lastUserFeedbackAt` after useful feedback is actually sent, increments
`outboxRevision` on meaningful delivery-state changes, and updates `quietUntil`
using the principal's timezone/quiet-hours policy. `renewAt` is the saved hook's
expiry minus a renewal margin; use a fresh value after renewal. Store the returned
hook ID/owner/expiry in the durable schedule ledger. Hook-local `hookState` is
dedup state, not the only copy of a long-lived obligation. Worker snapshots are
hashed into a fixed-width change fingerprint; raw note text is not retained in
hook state. The hash is a change detector, not a security or authorization check.

When delivery work remains, set `delivery` to the earliest outstanding obligation:
`{"id":"FINAL_REPLY_KEY","version":1,"dueAt":1730000000000}`. Use a stable outbox
key and advance `version` whenever an attempt, reconciliation or escalation
changes that obligation. `dueAt` is the next actionable deadline in epoch
milliseconds; the Python lifecycle example stores `next_at` in **seconds**, so
multiply it by 1000. Include pending sends, outcome-unknown reconciliation and
retry-exhaustion escalation. After each bounded processing pass, persist the next
deadline/version or select the next outstanding item. Set `delivery` to null only
when no delivery obligation remains. A wake is not an acknowledgement of delivery.

A due delivery obligation wakes Ada even when worker snapshots are unchanged,
during quiet hours, and after worker activity ends (`active: false`). The wake
only requests internal processing: reconcile ambiguous sends before retrying,
apply the channel's quiet-hours policy to user-facing messages, and keep the final
reply obligation open until resolved. The first validation run may wake for an
already-overdue obligation, but never sends a user message itself.

The hook suppresses repeated wakes for the same ID/version/deadline for 60 seconds.
If Ada crashes or the wake is lost, that wake lease expires and the still-pending
obligation wakes again. This is at-least-once recovery, not an exactly-once claim;
Ada must re-read the durable outbox and reconcile before acting. Acknowledging a
wake must not clear pending work: before a long processing attempt, persist an
advanced version with a recovery deadline; after processing, persist its result
and next obligation. Restore the earliest deadline from the durable outbox on
startup and reconcile the note after any interrupted update. If several items
are due, process a bounded batch and retain the earliest unfinished obligation.
These note updates are an adapter/owner responsibility; the example does not
connect the Python database to Intent automatically.

The hook reads passive worker status/task snapshots in parallel. It never calls
`ws.agent.send`, starts another Ada, or directly sends a user message. It runs at
30-second cadence with one-hour TTL. For progress, the immediate validation run
only establishes a baseline, preventing an accidental immediate “30-second” update. It dispatches
to its owner on meaningful changes, a first missing-feedback check or one bounded
five-minute reminder. Quiet hours defer nonurgent progress; renewal wakes are
internal maintenance and must not turn into unnecessary user messages. After an
inactive ledger with no pending delivery obligation, it asks Ada once to cancel
the hook. Delivery wakes do not consume the progress feedback/reminder clock or
lose changes deferred during quiet hours.

Task-note edits can be bookkeeping rather than useful progress. A hook dispatch is
therefore a request for Ada to evaluate feedback, not permission to forward raw
notes or every state change to the user. Ada checks the durable outbox/fingerprint
again before composing a concise message, so event and watchdog wakes cannot send
two replies. If necessary, inspect recent worker conversation passively with
`ws.agent.readConversation(agentId, { lastN: 4, includeToolCalls: false })`.

Prefer completion events via `ws.agent.watch(workerId)` for active workers, or
task/file events via the available `ws.event` APIs. `watch` delivers a one-shot wake
and is not proof of successful task completion: read the task result and evidence.
Consolidate active work in one watchdog and inspect `ws.hook.list()` before adding
more. The default cap is five active hooks per agent; do not spend one per worker
when a single passive check suffices.

## Renew schedules and recover after restart

Delay-based hooks have a 24-hour maximum TTL; cron hooks have a seven-day maximum.
`runAt` is a one-shot schedule with a fire-time grace period and cannot be combined
with `ttlMs` or `perpetual`. Restart does not reset expiry. Active hooks can resume
with their original deadlines; overdue hooks expire, and archived workspaces cancel
active hooks. Unarchiving does not resurrect them.

1. At startup/reconnect, load the durable channel binding and Ada identity, then
   inspect capabilities again. Reuse the recorded owner; reconcile a missing/stale
   identity before deliberately replacing it under a bootstrap lease.
2. Reconcile outcome-unknown external actions and sends against authoritative
   provider state before retrying. Resume the final-reply outbox independently of
   workers. Revalidate approval versions, expiry, revocation and cancellation.
3. Compare each still-authorized watch with `ws.hook.list({ includeRetired: true })`.
   Verify owner, actual state and `expiresAt`, rather than assuming a hook exists
   because its ID is in a note. `needs_renewal` in the Python example demonstrates
   the expiry predicate only.
4. Renew before expiry, when the operation remains authorized. Serialize renewal
   by watch ID and persist the replacement ID. Avoid running old and new watches
   concurrently; cancel your own replaced hook with `ws.hook.cancel(hookId)` and
   verify its state. If scheduling/cancellation has an unknown result, list and
   reconcile before retrying. Respect ownership; ask another owner to retire its hook.
5. After downtime, apply the watch's missed-run policy: reconcile current state and
   send one useful catch-up, not a burst of obsolete reminders. Record coverage gaps.
   A monthly reminder needs this durable renewal loop, not just a short-lived hook.

Each schedule record should hold purpose, source/query, owner task and agent,
trigger, last observed state, next due time, cooldown, timezone, authority expiry,
notification channel and stop condition. A supervisor/owner must revisit this
ledger on startup and before expiry; this pack does not install that supervisor.

## Verify and close

For every task, distinguish external action success from reply delivery. Inspect
provider receipts/state rather than trusting a worker's “done.” Keep the task in
verifying or explicitly blocked when the outcome is unknown. Record the exact
unfinished part, next action, owner and next check. A legitimate future follow-up
may remain active under a separate record after the current task completes.

On success, failure and cancellation, each worker retires its own temporary
files, tabs, sessions, holds, subscriptions, hooks and spawned processes. Preserve
deliverables, user-owned resources, receipts, correction history and authorized
follow-ups. Steward checks for orphans and confirms cleanup, or records why a
resource must remain. Cancelling an external commitment may cost money and needs
the applicable authority; it is not equivalent to stopping a local worker.

For disconnect-and-forget requests, stop connector use immediately, enumerate
derived notes/indexes/caches/watches, apply authorized deletion and report residual
provider backups/logs honestly. Disconnection alone is not deletion.

## Verification boundaries

`make check` validates generated specialist content and `make test` exercises the
offline pack/lifecycle contract. `python3 -m examples.demo` runs a no-network replay.
These do not launch Intent, connect WhatsApp or prove a staging connector's semantics.
Before autonomous use, verify installed composed prompts, identity/routing, idle
wakeup, inbound replay, ambiguous sends, receipt meaning, correction failure paths,
quiet hours, schedule expiry/restart, cancellation races and resource cleanup with
an explicitly authorized staging account. No-spend staging comes before bounded
real errands.
