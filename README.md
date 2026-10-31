# Personal assistant specialists for Intent

Twelve specialists for everyday planning, correspondence, research and follow-through.
Choose Pip for brief questions and chat, or Ada for ongoing coordination. Both can
consult the ten domain specialists; each request has one reply owner.
Start in your normal Intent conversation. An external channel such as WhatsApp is
optional; Ada discovers its actual capabilities before using it.

The pack also ships Intent's built-in **Assistant** (`chief-of-staff`), rewritten for
people who do not write code. Intent's app-level Assistant chat always starts this
specialist, and a replacement specialists directory removes Intent's own copy, so
without it the Assistant cannot start. It stays hidden from the specialist picker,
helps with the app in plain language and passes personal errands to your existing
Ada or Pip instead of doing them itself.

This repository contains **specialist instructions, offline reference examples and an
opt-in actual-agent evaluation harness**.
It does not install a messaging connector, authenticate accounts, receive webhooks,
enforce spending authority, or provide a production messaging bridge. The examples
exercise lifecycle decisions using fake transports, not live WhatsApp behavior.

| Specialist | Responsibility |
| --- | --- |
| Ada (`pa-ada`) | Durable coordination, priorities and ongoing commitments |
| Pip (`pa-pip`) | Brief questions, context consultation and accepted durable handoffs |
| Tempo (`pa-tempo`) | Calendar and commitments |
| Quill (`pa-quill`) | Correspondence and documents |
| Atlas (`pa-atlas`) | Travel and reservations |
| Scout (`pa-scout`) | Research and recommendations |
| Haven (`pa-haven`) | Home and personal logistics |
| Ledger (`pa-ledger`) | Bills and paperwork |
| Keeper (`pa-keeper`) | Memory and information |
| Sentinel (`pa-sentinel`) | Follow-ups and monitoring |
| Steward (`pa-steward`) | Operations and recovery |
| Auditor (`pa-auditor`) | Independent verification |
| Assistant (`chief-of-staff`, hidden) | Intent's app helper: finding conversations, settings and reaching Ada or Pip |

## Start here

1. Use an Intent daemon release that supports `serve --specialists-dir`; confirm
   support from its release documentation or source. Python 3.10+ runs the offline
   examples; the full test
   suite also uses Make and Node.js 18+ for the passive hook example.
2. Clone this repository with your GitHub access, then follow
   [installation and onboarding](docs/installation.md) to launch a dedicated PA
   environment and select Ada or Pip. Runtime personal records belong outside this checkout.
3. Run `make check`, `make test` and
   `python3 -m examples.demo` from the repository root for offline validation.
4. Use [the messaging capability contract](docs/messaging.md) before connecting
   an external channel. Follow [operations and recovery](docs/operations.md) for
   passive progress checks, final reply delivery, corrections and watch renewal.
5. Optionally select a dedicated private operational store for the team's records.
   [Internal Git collaboration](docs/operations.md#internal-records-handoffs-and-private-checkpoints)
   defines provenance, handoffs, agent-owned integration and verified checkpoints.
   The team handles routine Git work; personal decisions remain yours. This pack
   does not provision the store or install automatic sync/backup.

Each loaded team specialist contains the shared charter; the app Assistant does not,
because it is not a team member. The roster does not start twelve agents, and instruction text is not a permission boundary. External actions
need the principal's current authority and runtime/tool enforcement.

The replacement directory replaces Intent's base specialist bundle. User and
project overrides still apply, and shared/workspace instructions are composed
separately. See the installation guide before using this pack in an existing setup.

To change prompts, edit `source/` (team roles in `source/roles/`, the Assistant in
`source/assistant/`), run `make build`, then `make check` and
`make test`. Generated `specialists/` files are the installation artifacts.
Run `make test-watchdog` for just the Node.js passive hook tests.

Ada, Tempo and Auditor receive a shared [appointment-booking procedure](source/procedures/appointment-booking.md)
in their installed prompts. Run `make test-evals` for deterministic harness checks or
`make eval-actual EVAL_MODEL=<accessible-model-id>` for real inference against synthetic
services. See [evaluation setup, isolation and limitations](docs/evaluations.md). These
single-role sessions do not deploy connectors or prove live team orchestration.

Pip normally finishes in one or two exchanges. That is a working target, not an
automatic timeout. Longer tasks, unanswered decisions and late worker results need
a persisted handoff accepted by a durable owner before Pip relinquishes ownership.
An unavailable owner is reported plainly, with work retained as pending. Installing
these instructions does not install a router, handoff service or automatic retirement.
See [brief-chat operation](docs/operations.md#brief-chat-and-durable-handoff).
`make test-chat` tests synthetic services and the scorer; `make eval-chat EVAL_MODEL=<accessible-model-id>` runs actual Pip inference against those fake tools.
