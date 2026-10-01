# Installation and first conversation

## Install in a dedicated environment

Use an Intent daemon release with `serve --specialists-dir`, a configured model
provider, and a dedicated OS account or container for the PA. This pack does not
install Intent or model credentials. Confirm flag support from the matching release
documentation or source. Do not probe a shared installed launcher with help commands:
the launcher may manage supervisor runtime files even when asked for help. If a
binary probe is necessary, use an explicitly isolated bare daemon executable.

Clone the private repository with your authorized GitHub identity. Run the offline
checks from its root with Python 3.10+, Make and Node.js 18+:

```sh
make check
make test
python3 -m examples.demo
```

`make test` runs Python with `-S` to avoid host site instrumentation and includes
the Node.js hook tests. `make test-watchdog` runs just those hook tests with
`node --test`.

Keep the pack checkout separate from the PA workspace and all personal runtime
data. In the dedicated account, the following shell example uses the current
checkout's `specialists/` directory and creates private runtime storage:

```sh
PA_PACK_DIR="$(pwd)"
PA_RUNTIME_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/intent-pa"
umask 077
mkdir -p "$PA_RUNTIME_DIR/data" "$PA_RUNTIME_DIR/workspace"
export INTENTD_DATA_DIR="$PA_RUNTIME_DIR/data"
export INTENTD_CONFIG="$PA_RUNTIME_DIR/config.toml"
intentd serve --specialists-dir "$PA_PACK_DIR/specialists"
```

Configure the dedicated daemon through the installed Intent setup flow before
connecting accounts. Keep its TCP listener disabled unless you have configured
the supported authenticated transport. Never use `--insecure` for this deployment.
Do not inherit an `INTENTD_INSECURE` development setting. Data/config paths alone
do **not** isolate home-directory specialist overrides, credentials or environment
variables. A separate OS account/container and scoped credentials provide those
boundaries. Disable workspace auto-commit for personal runtime work; never put
private notes, SQLite ledgers or account exports into the pack's Git history.

`INTENTD_SPECIALISTS_DIR` is the environment alternative to the launch flag. The
flag takes precedence. This replaces the whole base tier, including the bundled
coding specialists; it is not an additive pack install. User definitions in
`~/.intent/specialists/` and project definitions in `.intent/specialists/` can still
override it. A missing or empty replacement directory means an empty base tier.
The replacement directory is static: restart the daemon and create fresh test
sessions after changing prompts. Existing sessions can retain their earlier prompt.

## Bootstrap Ada

Starting the daemon exposes the catalog; it does not create Ada or connect any
messaging account. In the dedicated environment:

1. Create or reuse one PA workspace rooted in the separate runtime workspace.
   Inspect its shared/project instructions for development rules that would
   conflict with personal assistant work.
2. Verify that all eleven `pa-*` IDs appear in the specialist catalog. Select
   `pa-ada` as the human-facing orchestrator when creating its conversation.
3. Record that workspace and Ada agent identity in a private routing ledger.
   On subsequent startup, resolve the recorded identity first. Do not create a
   fresh Ada merely because she is idle. A bootstrap service must serialize
   creation with a durable lease and reconcile a timed-out create before retrying.
4. Use the current human-facing Intent conversation immediately if no external
   channel is configured. Ask onboarding questions there; WhatsApp is not a
   prerequisite. Do not create another agent to serve as a second conversation owner.
5. If an external channel is configured, verify its account, the authenticated
   principal and one direct thread, then persist that binding. Send replies through
   that selected channel. Follow the capability checks below after reconnect too.

Base replacement does not remove shared Git/commit/project rules or generic
delegation examples. Inspect an actual fresh composed session: select `pa-*` role
IDs explicitly, since an example's generic coding `implementor` may not exist in
this catalog. External-channel replies must use ordinary text or supported secure
links; Intent-only cards and internal rich links are not usable there. Resolve
instruction conflicts in the dedicated workspace before autonomous use.

The offline lifecycle's `bind_owner` demonstrates retaining an existing routing
identity across restart. It does not create, lease, discover or resume Intent
agents. A live bootstrap must supply those operations using the installed API.
Do not enable `serve --resume-all` until ambiguous-write recovery has been tested:
it force-resumes interrupted agents, rather than authorizing duplicate actions.

## Onboard only what is needed

Ask for timezone and language, preferred short-message style, quiet hours and
urgent exceptions, active commitments, and which accounts the user wants to
connect. Defaults are preparation and reversible internal organization; existing
concrete instructions can authorize bounded external actions without redundant
approval. Standing mandates need explicit scope, recipients, total/currency,
period, expiry, exclusions and revocation rules.

Keep a compact principal profile, current-task/watch index and canonical entity
records with provenance and review dates. Store secrets only in the supported
credential service. Do not ask the user to paste passwords or authentication codes
into a note or conversation. Each worker gets only the context needed for its task.

## Discover messaging capabilities

These are real Intent workspace API calls, verified against its runtime help.
They are snippets for an agent's `workspace_api` tool, not shell commands:

```javascript
return await ws.mcp.listServers();
```

Choose the configured server from that response, then inspect its schemas:

```javascript
const serverId = "REPLACE_WITH_CONFIGURED_SERVER_ID";
return await ws.mcp.listTools(serverId);
```

Only after reviewing a real schema should the adapter use
`ws.mcp.callTool(serverId, toolName, args, timeoutMs)`. There is deliberately no
guessed WhatsApp send method here. Record verified capabilities using the
[capability table](messaging.md). A `send` tool alone says nothing about incoming
wakeups, reactions, edit/delete semantics, message search or read receipts.

For a headless PA, an embedded Intent browser is not automatically available:
it is rendered by a connected desktop client. Browser-dependent errands need a
separately verified headless browser connector or a direct service API.

## First acceptance run

Start with an internal, reversible task such as drafting tomorrow's plan. Confirm
Ada receives the request, delegates only when useful, reports progress without
interrupting workers, and returns one final answer. For an external channel, use
an explicitly authorized staging conversation to test authentication, replay,
timeout recovery and receipts before enabling real errands. Installing this pack
does not authorize account connection, live messages or spending.

To roll back, stop inbound task creation, retire owned watches, reconcile pending
writes and outbox entries, then stop the dedicated daemon and restore its previous
specialist configuration. Prompt rollback cannot undo a sent message or purchase;
use recorded cancellation/compensation procedures within the user's authority.
