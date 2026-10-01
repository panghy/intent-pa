"""Bounded stdio client for the documented Codex app-server dynamic-tool API."""

import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import tempfile
import threading
import time


class ProviderError(RuntimeError):
    """Missing provider, incompatible interface, or incomplete inference."""


def isolated_command(work):
    """Mount only runtime libraries, TLS/DNS and CLI-owned auth, never the repo/home."""
    binary, bubblewrap = shutil.which("codex"), shutil.which("bwrap")
    if not binary or not bubblewrap:
        raise ProviderError("Actual evaluations require Codex CLI and Linux bubblewrap (bwrap).")
    home = Path.home()
    codex_home = Path(os.environ.get("CODEX_HOME", str(home / ".codex"))).resolve()
    auth = codex_home / "auth.json"
    if not auth.is_file():
        raise ProviderError("No file-backed Codex login. Run codex login before actual evaluations.")
    command = [bubblewrap, "--die-with-parent", "--new-session", "--unshare-pid",
               "--clearenv", "--setenv", "PATH", "/usr/bin:/bin",
               "--setenv", "HOME", str(home), "--setenv", "CODEX_HOME", str(codex_home),
               "--setenv", "LANG", "C.UTF-8", "--proc", "/proc", "--dev", "/dev",
               "--tmpfs", "/tmp", "--dir", str(codex_home),
               "--ro-bind", str(auth), str(auth),
               "--bind", str(work), "/work", "--chdir", "/work"]
    for path in ("/usr", "/bin", "/lib", "/lib64", "/etc/ssl", "/etc/resolv.conf", "/etc/hosts"):
        if Path(path).exists():
            command += ["--ro-bind", path, path]
    host = Path(binary).resolve().with_name("codex-code-mode-host")
    if not host.is_file():
        raise ProviderError("Codex code-mode runtime is missing; reinstall the complete Codex CLI package.")
    command += ["--ro-bind", str(host), "/opt/codex-code-mode-host",
                "--ro-bind", str(Path(binary).resolve()), "/opt/codex", "/opt/codex",
                "app-server", "--listen", "stdio://"]
    for feature in ("shell_tool", "unified_exec", "shell_snapshot", "apps", "plugins",
                    "remote_plugin", "multi_agent", "browser_use", "browser_use_external",
                    "computer_use", "image_generation", "hooks", "memories", "skill_search"):
        command += ["-c", f"features.{feature}=false"]
    command += ["-c", 'web_search="disabled"', "-c", 'approval_policy="never"',
                "-c", 'sandbox_mode="read-only"', "-c", "project_doc_max_bytes=0",
                "-c", 'model_provider="openai"']
    return command


class CodexSession:
    """One owned child process and temporary filesystem per scenario; no global kills."""

    def __init__(self, timeout=180):
        self.timeout = timeout
        self.events = []
        self.next_id = 0
        self.inbox = queue.Queue()
        self.temp = None
        self.process = None

    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pa-agent-eval-")
        try:
            command = isolated_command(Path(self.temp.name))
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.DEVNULL, text=True, start_new_session=True)
            self.deadline = time.monotonic() + self.timeout
            self.reader = threading.Thread(target=self._read, daemon=True)
            self.reader.start()
            self.request("initialize", {"clientInfo": {"name": "pa_evals", "version": "1.0"},
                                        "capabilities": {"experimentalApi": True}})
            self.send({"method": "initialized", "params": {}})
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _read(self):
        try:
            for line in self.process.stdout:
                self.inbox.put(json.loads(line))
        except (ValueError, OSError) as exc:
            self.inbox.put({"reader_error": type(exc).__name__})
        finally:
            self.inbox.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def receive(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProviderError("Actual-agent session deadline exceeded.")
        try:
            item = self.inbox.get(timeout=remaining)
        except queue.Empty as exc:
            raise ProviderError("Actual-agent session deadline exceeded.") from exc
        if item is None or "reader_error" in item:
            raise ProviderError("Codex app-server closed or returned malformed output; check CLI compatibility/login.")
        self.events.append(item)
        if len(self.events) > 10000:
            raise ProviderError("Session event budget exceeded.")
        return item

    def request(self, method, params):
        self.next_id += 1
        request_id = self.next_id
        self.send({"id": request_id, "method": method, "params": params})
        while True:
            item = self.receive()
            if item.get("id") == request_id and "method" not in item:
                if "error" in item:
                    raise ProviderError(f"Codex rejected {method}: {item['error'].get('message', 'RPC error')}")
                return item["result"]
            if "id" in item and "method" in item:
                raise ProviderError("Unexpected server request before inference.")

    def run(self, model, body, prompt, tools, dispatch, max_calls=24, output_schema=None, observe_message=None):
        started = self.request("thread/start", {
            "model": model, "modelProvider": "openai", "allowProviderModelFallback": False,
            "ephemeral": True, "cwd": "/work", "environments": [],
            "approvalPolicy": "never", "sandbox": "read-only",
            "baseInstructions": body, "dynamicTools": tools,
        })
        if started["model"] != model or started.get("instructionSources"):
            raise ProviderError("Unexpected model fallback or host instruction contamination.")
        self.metadata = {"provider": started["modelProvider"], "model": started["model"]}
        thread_id = started["thread"]["id"]
        self.request("turn/start", {"threadId": thread_id, "environments": [],
                                   "effort": "low", "outputSchema": output_schema,
                                   "input": [{"type": "text", "text": prompt}]})
        messages, calls = [], 0
        while True:
            event = self.receive()
            method, params = event.get("method"), event.get("params", {})
            if method == "item/tool/call":
                calls += 1
                if calls > max_calls:
                    raise ProviderError("Actual-agent tool-call budget exceeded.")
                output = dispatch(params["tool"], params["arguments"])
                self.send({"id": event["id"], "result": {"success": True, "contentItems": [
                    {"type": "inputText", "text": json.dumps(output)}]}})
            elif "id" in event and method:
                raise ProviderError(f"Unexpected server request {method}; no real tool approval is allowed.")
            elif method == "item/completed":
                item = params["item"]
                if item["type"] == "agentMessage":
                    message = {"text": item["text"], "phase": item.get("phase")}
                    messages.append(message)
                    if observe_message:
                        observe_message(message)
                elif item["type"] not in {"userMessage", "reasoning", "plan", "dynamicToolCall", "functionCallOutput", "contextCompaction"}:
                    raise ProviderError("Isolation failure: a non-fake tool was used.")
            elif method == "turn/completed":
                if params["turn"]["status"] != "completed":
                    error = params["turn"].get("error") or {}
                    raise ProviderError("Inference failed: " + str(error.get("message", params["turn"]["status"])))
                if not messages:
                    raise ProviderError("Model returned no user-facing answer.")
                return messages

    def __exit__(self, *_):
        if self.process:
            if self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(self.process.pid, signal.SIGKILL)
                    self.process.wait(timeout=3)
                except ProcessLookupError:
                    pass
            for stream in (self.process.stdin, self.process.stdout):
                if stream:
                    stream.close()
        if self.temp:
            self.temp.cleanup()
