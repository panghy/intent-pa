# Personal assistant specialists for Intent

Eleven specialists for everyday planning, correspondence, research and follow-through.
Ada owns the conversation and delegates bounded work to ten specialists on demand.
Start in your normal Intent conversation. An external channel such as WhatsApp is
optional; Ada discovers its actual capabilities before using it.

This repository contains **specialist instructions, offline reference examples and an
opt-in actual-agent evaluation harness**.
It does not install a messaging connector, authenticate accounts, receive webhooks,
enforce spending authority, or provide a production messaging bridge. The examples
exercise lifecycle decisions using fake transports, not live WhatsApp behavior.

| Specialist | Responsibility |
| --- | --- |
| Ada (`pa-ada`) | Conversation, priorities, delegation and final replies |
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

## Start here

1. Use an Intent daemon release that supports `serve --specialists-dir`; confirm
   support from its release documentation or source. Python 3.10+ runs the offline
   examples; the full test
   suite also uses Make and Node.js 18+ for the passive hook example.
2. Clone this repository with your GitHub access, then follow
   [installation and onboarding](docs/installation.md) to launch a dedicated PA
   environment and select Ada. Runtime personal records belong outside this checkout.
3. Run `make check`, `make test` and
   `python3 -m examples.demo` from the repository root for offline validation.
4. Use [the messaging capability contract](docs/messaging.md) before connecting
   an external channel. Follow [operations and recovery](docs/operations.md) for
   passive progress checks, final reply delivery, corrections and watch renewal.

Each loaded specialist contains the shared charter. The roster does not start
eleven agents, and instruction text is not a permission boundary. External actions
need the principal's current authority and runtime/tool enforcement.

The replacement directory replaces Intent's base specialist bundle. User and
project overrides still apply, and shared/workspace instructions are composed
separately. See the installation guide before using this pack in an existing setup.

To change prompts, edit `source/`, run `make build`, then `make check` and
`make test`. Generated `specialists/` files are the installation artifacts.
Run `make test-watchdog` for just the Node.js passive hook tests.

Ada, Tempo and Auditor receive a shared [appointment-booking procedure](source/procedures/appointment-booking.md)
in their installed prompts. Run `make test-evals` for deterministic harness checks or
`make eval-actual EVAL_MODEL=<accessible-model-id>` for real inference against synthetic
services. See [evaluation setup, isolation and limitations](docs/evaluations.md). These
single-role sessions do not deploy connectors or prove live team orchestration.
