"""Opt-in actual Pip inference with synthetic ownership/consultation tools."""

import argparse
from datetime import datetime, timezone
import json
import subprocess
import uuid

from evals.chat import ADAPTER, CASES, FINAL, TOOLS, ChatWorld, score_chat
from evals.codex import CodexSession, ProviderError
from evals.run import ROOT, digest


def compose_chat(case):
    content = (ROOT / "specialists/pa-pip.md").read_text()
    body = content[4:].split("\n---\n", 1)[1].strip()
    prompt = ADAPTER + "\nInvocation: " + ("internal from Ada" if case.kind == "internal" else "direct principal") + "\nRequest: " + case.request
    return body, prompt, {"role_file": digest(content), "role_body": digest(body),
                          "input": digest(prompt), "followup": digest(case.followup),
                          "tools": digest(TOOLS), "final_schema": digest(FINAL)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--scenario", action="append", choices=[s.id for s in CASES])
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    if not 10 <= args.timeout <= 300:
        parser.error("--timeout must be between 10 and 300 seconds")
    selected = [s for s in CASES if not args.scenario or s.id in args.scenario]
    now = datetime.now(timezone.utc)
    destination = ROOT / ".runtime/evals" / (now.strftime("%Y%m%dT%H%M%SZ") + "-chat-" + uuid.uuid4().hex[:8])
    destination.mkdir(parents=True, mode=0o700)
    report = {"started_at": now.isoformat(), "integration": "codex-app-server-dynamic-tools",
              "session_scope": "actual Pip inference; synthetic workers, acknowledgement and channel; no Intent orchestration",
              "requested_model": args.model, "reasoning_effort": "low", "timeout_seconds": args.timeout, "max_calls": 24,
              "harness_hashes": {p.name: digest(p.read_text()) for p in sorted((ROOT / "evals").glob("*.py"))},
              "not_run": [s.id for s in CASES if s not in selected], "scenarios": []}
    exit_code = 0
    try:
        report["cli_version"] = subprocess.run(["codex", "--version"], capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        for case in selected:
            body, prompt, hashes = compose_chat(case)
            world = ChatWorld(case, destination / (case.id + ".state.json"))
            row = {"id": case.id, "role": "pa-pip", "input_hashes": hashes,
                   "scenario_hash": digest(vars(case)), "world_input_hash": digest(world.context())}
            turns = []
            try:
                with CodexSession(args.timeout) as session:
                    turns.append(session.run(args.model, body, prompt, TOOLS, world.dispatch,
                                             output_schema=FINAL, observe_message=world.observe))
                    if case.followup:
                        world.next_turn()
                        turns.append(session.continue_turn(case.followup + "\nCurrent reply_id: reply-2.", world.dispatch,
                                                           output_schema=FINAL, observe_message=world.observe))
                    row.update(session.metadata)
                row.update(score_chat(world, turns), execution="completed", turns=len(turns))
                exit_code = max(exit_code, 0 if row["passed"] else 1)
            except (ProviderError, OSError, subprocess.SubprocessError) as exc:
                row.update(execution="provider_error", passed=False, failures=[str(exc)])
                exit_code = 2
            trace = json.dumps(world.trace, indent=2) + "\n"
            (destination / (case.id + ".trace.json")).write_text(trace)
            row["trace_sha256"] = digest(trace)
            report["scenarios"].append(row)
            (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"{case.id}: {'PASS' if row['passed'] else 'FAIL'} {', '.join(row['failures'])}", flush=True)
            if row["execution"] == "provider_error":
                report["not_run"] += [s.id for s in selected if s.id not in {r["id"] for r in report["scenarios"]}]
                break
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report["provider_error"] = str(exc)
        report["not_run"] = [s.id for s in CASES]
        exit_code = 2
    finally:
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        (destination / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(f"Evidence: {destination.relative_to(ROOT)}/report.json", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
