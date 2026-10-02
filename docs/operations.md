# Progress, delivery and recovery

Keep a private task/action ledger, channel binding, outbox, schedule ledger and
resource registry. Store IDs and compact facts with provenance; keep credentials
in the credential service and original documents in their authoritative systems.
Ada owns ongoing replies; direct Pip owns its brief request/thread. Workers return
evidence and cleanup status to the current requester, never a duplicate user send.

## Internal records, handoffs and private checkpoints

This is a team operating procedure, not a shipped Git service. The installed
charter contains the essential rules; the details here guide setup and review.
No executable Git workflow or automatic checkpoint scheduler is installed.

### Destination and authority

The principal selects a dedicated private operational repository; never assume
this pack's repository is that destination. Steward records its stable repository
identity, owner, URL, intended integration branch and last privacy/access check.
Before the first upload, after reconnect and before each push, check those against
the authenticated account and current remote metadata, including collaborator
access and applicable branch restrictions. A renamed/transferred repository or
changed audience needs reconciliation, not blind trust in a familiar URL.

Store selection authorizes minimized task records, personal facts and redacted
checkpoints needed for the service. It does not authorize bulk account exports,
uploading pre-existing history or disclosure to extra collaborators. Never store
credentials, access tokens, payment secrets, raw sensitive archives or full
transcripts in tracked files, Git metadata or logs. Use opaque task IDs in branch
names and commit messages. Private hosting is access control, not encryption or
proof that every copy is erasable. Review content and metadata before staging;
ignore rules and automated secret scans are useful but not a privacy boundary.

Use the actual installed Intent Git helpers for attributed, explicitly scoped
commits where available; inspect their supported arguments and repository root
selection first. Read history/diffs with available read-only Git tools for
provenance. Use only supported interfaces for branches, worktrees and remotes.
No method name in this procedure implies an API exists. If the available commit
helper cannot scope the intended root/files, stop that write and resolve setup.
Never bypass an enforced approval or disable policy to satisfy this pack.

Routine internal review and synchronization belong to agents. PRs are optional
coordination, not a routine user chore. If inherited development merge rules or
branch protection prevent autonomous store integration, preserve local work and
have Ada explain the required access/configuration change. Do not repeatedly ask
the principal to approve operational diffs. Pack development remains subject to
its own review and human merge rules.

### Record map and field authority

Keeper maintains one manifest mapping stable task and note IDs to record IDs,
canonical locations, owners and original sources. Notes remain searchable working
records with pointers and last-seen versions. Changes in notes are proposals to
the canonical owner until accepted; a stale note cannot overwrite current state.
The hierarchy in the charter determines retrieval order, not permission precedence.

| Information | Canonical authority | Store representation |
| --- | --- | --- |
| Profile and curated entity facts | Integrated records maintained by Keeper; authenticated corrections supersede earlier facts | Compact profile, entity IDs, source pointers and conflicting observations |
| Principal intent and action authority | Current authenticated request and durable authority ledger, checked for expiry/revocation | Authority index and versioned references; never a reusable approval token |
| Task status, action attempts and unknown outcomes | Current durable runtime task/action ledger | Consistent minimized checkpoint with generation/source versions |
| Outbox, handoff acknowledgements, watches and resources | Respective durable runtime ledgers with one accountable owner | Indexes and recovery checkpoints, not live writable replicas |
| Whether an external action occurred | Current authoritative provider record | Receipt/reference plus observed time and reconciliation status |
| Decisions, verified outcomes and archive | Append-only event records and linked evidence; corrections supersede events | Event IDs, concise closed-task summaries, unresolved obligations |

Each record needs `id`, `schema_version`, `version`, `owner`, `task_id`,
`authority_ref`, source references and observation time, fact/inference status,
sensitivity and review/expiry (explicitly not-applicable where appropriate).
Each fact retains its own provenance; rewriting a summary must not manufacture a
new observation date. Decision/outcome events include actor, task/action version,
evidence and any superseded event ID. Append-only is the normal audit policy,
subject to authorized retention/deletion; it is not a claim of immutable truth.
Keeper reviews schema migrations; Auditor checks consequential changes before
Steward integrates them. Unknown schemas are quarantined for review, not guessed.

A checkpoint manifest includes schema version, generation ID, capture time,
source ledger versions/watermarks, included record IDs and content checksums,
exclusions, pending obligations and a reference to the current retention policy.
Export a transactionally consistent snapshot from runtime storage through its
supported export/backup mechanism; never copy a live SQLite file into Git. If
consistency cannot be established, retain work locally and label backup incomplete.
A checkpoint may omit protected data intentionally: say exactly what is restorable.
Restoring indexes cannot reconstruct excluded documents or credential services.

### Worker handoff and integration

The entrypoint assigns the task/version, bounded authority and success condition. A worker
starts from the recorded integrated base and record versions. Parallel workers
use separate scoped worktrees/branches when supported; otherwise Steward
serializes editing and attributed commits in the shared checkout. Never switch
its branch under another worker. Keep branch/worktree ownership in the resource
registry. Each change names its task and modifies only that task's records.

Persist the handoff in the durable inbox before any event notification. Include
handoff ID/version, task/version, sender and intended recipient, base checkpoint,
affected record IDs and expected versions, proposed changes and evidence, result,
unfinished obligations, next owner/action/check time and cleanup status. Link the
private change summary and checkpoint where available; absent integration/backup
is an explicit pending state, not a reason to lose an otherwise useful handoff.

The recipient re-reads the durable record, validates schema, sender/scope, task
and authority freshness, base and record versions, and acknowledges the exact
handoff ID/version after reading it. Record accepted, needs-correction or blocked
with a reason and next owner. Acknowledged means received and checked, not merged,
externally executed or delivered to the user. Duplicate wakes look up that same
acknowledgement. Superseded versions cannot regain authority. Rejection retains
the original and pending correction obligation; silence leaves it pending.

Steward serializes integration, fetching the current base and reviewing semantic
changes before applying them. Recheck affected versions immediately before
integration, even after an internal review. Non-overlapping changes can proceed;
conflicting facts or authority require owner reconciliation and, if necessary,
Auditor review. Ada asks the principal only about unresolved personal intent.
Record the resolution with both sources. Never silently choose the latest
written value, even when Git reports no textual conflict. Internal approval of a
record has no effect on external action permission.

### Checkpoints, outages and restore

Steward checkpoints at accepted handoffs, verified outcomes, material memory
changes and graceful shutdown. During active dirty work, record a next checkpoint
deadline (default five minutes); coalesce it with the existing maintenance watch.
Persist the due work outside hook state, renew the watch and reconcile overdue
work on startup. A scheduling failure is a coverage gap, not successful backup.
The pack does not install that export/maintenance loop.

Validate schema, privacy and consistency, stage only the intended files, integrate,
then push only to the verified destination. After a push or uncertain response,
read the remote ref and confirm it contains the intended checkpoint and manifest.
Record the verified checkpoint, coverage, last successful time, and outstanding
local generations. A local commit, queued push or clean worktree is not remote
backup evidence. Fetch and reconcile remote divergence; never force-push, discard
local edits or overwrite remote work to make a status indicator green.

On a known transient failure, retain a durable sync obligation and retry after
one, five and fifteen minutes, then pause and notify Ada of the outage. Record
attempts/deadlines; after exhaustion wait for a meaningful recovery/access change
rather than loop. Missing destinations, unverified privacy or denied access stop
uploads immediately until corrected. Continue safe local work when its durable
storage is available; otherwise report the capability gap. Never create a public
fallback, upload to the pack repo or claim local work is remotely backed up.

Remote synchronization and independently restorable backup are different claims.
At first setup, after schema/storage changes and periodically (default monthly),
Steward restores a retained checkpoint into isolated private storage with outbound
actions disabled. Validate schema, manifest/checksums, source versions, reference
integrity, coverage and current retention exclusions; record time, result and
missing dependencies. Do not overwrite live state during a drill. A remote-only
copy shares account/deletion risks; an independent backup destination needs its
own authorized privacy, retention and restore checks before being called a backup.

After a real restore, preserve any newer local work. Compare the restored state
with current principal instructions and forgetting records, then read provider
state for unknown writes and pending sends, revalidate authority, reconcile
handoffs and renew still-authorized schedules. Git history is neither a lease nor
proof a payment/message did not happen. Unknown or unrecoverable state stays
paused for reconciliation; never replay old approvals or sends. Restore does
not rewind external reality. Only then resume eligible work and separately
reconcile Ada's final-reply obligation.

Remove owned temporary exports and worktrees only after verified integration,
required checkpoint coverage and settled handoff/action/delivery obligations.
Retain unmerged or unpushed work with an owner and next action, even after a task
is cancelled. Never remove another worker's/user's resources as cleanup.

### Worked recovery examples

These are walkthroughs for reviewers, not executed Git or multi-agent tests.

| Situation | Required handling | User-facing result if needed |
| --- | --- | --- |
| Two workers edit entity E7 from version 4; one corrects a phone number, another adds a preferred appointment time | Integrate the verified phone correction as version 5; re-read/review the time proposal against version 5 before version 6. Preserve both provenance entries. If both changed the same preference, retain both sources and ask Ada to resolve meaning rather than accept a clean textual merge. | “Do you prefer morning or afternoon appointments now?” only if current sources cannot resolve intent. |
| Handoff H9 lacks evidence or expects a superseded task/authority version | Record needs-correction for H9's exact version; keep its pending obligation, return the reason to its owner and request a new validated version. No integration or external action follows stale authority. | Usually none; Ada asks only if the personal decision is still missing. |
| Remote is missing, inaccessible or its private status cannot be verified | Preserve local records and pending sync. Stop uploads until destination/privacy/access is verified; bounded retry only for transient failures. | “Your work is saved locally, but I cannot update your private backup. Please reconnect access.” Do not say saved locally unless confirmed. |
| Crash after persisting a handoff, before notification/acknowledgement | On restart scan pending inbox and acknowledgements by ID/version, notify again if needed, and let recipient deduplicate. A committed record alone is not acknowledgement. | None unless the outage affects the requested outcome. |
| Remote advanced or a push timed out | Fetch/read remote history, locate the intended checkpoint, then reconcile other edits. Confirm coverage or retain a pending push; no force-push or duplicate checkpoint claim. | “Your latest changes are still waiting to be backed up.” |
| Restore contains an old approval and a send marked pending | Validate against current authority and provider state before any send; reconcile existing message IDs and leave unknown outcomes paused. Keep any forgotten facts excluded. | State the unresolved personal outcome, not the restored revision. |

### Retention and forgetting

Keeper tracks retention by record, source and derived copy; Steward applies it to
checkpoints, clones, caches and restore procedures. Stop new use, indexing, sync
and pending watches in scope immediately. Remove authorized current copies and
keep a minimal opaque deletion marker under the retention policy so a later
restore cannot silently resurrect the fact. Do not put the forgotten value in
that marker. Resolve expired deletion markers against retained old backups before
removing the markers themselves.

Deleting a file or reverting a commit leaves historical copies. History rewriting
is a separate coordinated privacy operation with explicit authority and verified
scope, not routine sync cleanup; this workflow never force-pushes. Inventory remote
history, collaborators' clones, provider retention and independent backups and
report what cannot be verified or erased. Disconnecting access is not deletion.
For a leaked secret, stop propagation, use the supported revocation/rotation flow,
and involve the appropriate owner; removing text does not revoke a credential.


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


## Brief chat and durable handoff

Select Pip for a one-off question. It can answer directly, read a relevant shared
record, ask an existing specialist, or delegate a bounded task. One or two exchanges
is a target; an unanswered follow-up is not discarded. It reads existing profile
context rather than repeating onboarding, and does not turn casual chat into memory.
Explicit durable preferences go to Keeper with source context and a responsible owner.

Exactly one reply owner is recorded per request/thread. A directly selected Pip
answers there. An internally called Pip returns its result to the requester. Ada
continues to own other ongoing threads; selecting Pip is not a global channel rebind.
The Ada-specific watchdog and lifecycle examples above remain durable-owner examples,
not a background service that Pip starts for every question.

Before launching work that may outlive the exchange, persist a recovery record.
Before leaving it, obtain a durable recipient's explicit acknowledgement of the
current handoff ID/version. Include the source channel/thread/message, principal and
authority reference, task/version, evidence pointers, worker IDs and result records,
pending decisions/actions, unknown writes, outbox/reply state and next sender,
resource owners, next action and check time. A task assignment, notification, Git
commit or queued message is not acceptance. Do not create another follow-up on every
retry. Preserve corrected facts and late results in the existing canonical records.

Only after acceptance may the ownership record change. Ada reads late worker results
from those records and establishes any required subscriptions using its own supported
tools before Pip cleans up its own watch. Never impersonate another resource owner,
assume a hook's ownership can be changed, or delete an unsent reply. The accepting
owner sends the remaining response; Pip does not send the same response too.

If transfer fails or tools cannot support it, keep a pending handoff under the original
owner with reason and recovery action. Explain the lack of automatic follow-through
in plain language. Ending a blocked turn is not successful retirement: never delete
the session or claim monitoring is active. If persistence is unavailable, disclose it
and avoid launching unrecoverable asynchronous work. Restart recovery reconciles the
current authority, writes, replies and acknowledgement before any replay.

The supported Intent surfaces inspected for these instructions are `ws.agent.list`,
`ws.note.listTasks`, `ws.agent.delegate`, `ws.agent.send(..., "queue")`, read-only
agent status/conversation, notes, watches and owner-scoped cleanup. None is a dedicated
atomic PA transfer API. Implementations must supply validated durable acknowledgements
and serialized ownership before deploying this contract. The evaluation tools named
`chat_*` are synthetic adapters only; they are not Intent APIs. The pack itself does
not enforce lifetime, transfer atomicity, routing, recovery or delivery.
