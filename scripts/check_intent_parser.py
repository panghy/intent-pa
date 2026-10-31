#!/usr/bin/env python3
"""Run the actual Intent frontmatter/roster parser in a disposable Rust fixture.

Requires a locally supplied source file, Cargo, and cached serde_json dependencies.
Does not modify that source checkout, start a daemon, connect accounts, or test
the full catalog overlay/session composition path. Parser code is never vendored.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from build_pack import GENERATED_IDS, ROOT, intent_metadata, parse_generated, validate


def function(source, name):
    pattern = rf"^(?:pub\(crate\) )?fn {re.escape(name)}\([^\n]*\)[^\n]*\{{\n.*?^\}}"
    match = re.search(pattern, source, re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"Cannot extract {name}; review upstream parser changes")
    return match.group(0)


def fixture_source(source):
    retired = re.search(r"^const RETIRED_FRONTMATTER_KEYS:.*?;", source, re.MULTILINE | re.DOTALL)
    if not retired:
        raise ValueError("Cannot find retired frontmatter keys; review upstream parser changes")
    functions = [function(source, name) for name in (
        "unescape_yaml", "parse_frontmatter", "parse_team_agents_frontmatter",
    )]
    return "\n\n".join([
        "use serde_json::{json, Map, Value};", retired.group(0), *functions,
        '''fn main() {
    let mut output = Vec::new();
    for filename in std::env::args().skip(1) {
        let content = std::fs::read_to_string(&filename).expect("read fixture");
        let (mut metadata, prompt) = parse_frontmatter(&content);
        if let Some(raw) = metadata.get("teamAgents").and_then(Value::as_str) {
            let roster = parse_team_agents_frontmatter(raw).expect("valid roster");
            metadata.insert("teamAgents".into(), json!(roster));
        }
        let id = std::path::Path::new(&filename).file_stem().unwrap().to_str().unwrap();
        output.push(json!({"id": id, "metadata": metadata, "prompt": prompt}));
    }
    println!("{}", serde_json::to_string(&output).unwrap());
}''',
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    validate()
    source = args.source.read_text(encoding="utf-8")
    rust = fixture_source(source)
    with tempfile.TemporaryDirectory(prefix="pa-parser-") as temporary:
        directory = Path(temporary)
        (directory / "src").mkdir()
        (directory / "Cargo.toml").write_text(
            '[package]\nname = "pa-parser-fixture"\nversion = "0.1.0"\nedition = "2021"\n'
            '[dependencies]\nserde_json = "1"\n', encoding="utf-8",
        )
        (directory / "src/main.rs").write_text(rust, encoding="utf-8")
        files = sorted((ROOT / "specialists").glob("*.md"))
        # Keep build output inside the disposable fixture even with a shared
        # CARGO_TARGET_DIR configured by the caller.
        environment = dict(os.environ, CARGO_TARGET_DIR=str(directory / "target"))
        result = subprocess.run(
            ["cargo", "run", "--offline", "--quiet", "--manifest-path",
             str(directory / "Cargo.toml"), "--", *map(str, files)],
            cwd=directory, env=environment, text=True, capture_output=True, timeout=120,
        )
        if result.returncode:
            raise SystemExit(f"Actual parser fixture failed:\n{result.stderr}")
        loaded = json.loads(result.stdout)
        if len(loaded) != len(GENERATED_IDS) or {item["id"] for item in loaded} != GENERATED_IDS:
            raise SystemExit("Actual parser did not return the twelve team specialists and the app assistant")
        for path, item in zip(files, loaded):
            expected_metadata, expected_prompt = parse_generated(path.read_text(encoding="utf-8"))
            if item["metadata"] != intent_metadata(expected_metadata) or item["prompt"] != expected_prompt:
                raise SystemExit(f"Actual parser changed metadata or prompt body: {path.name}")
    fingerprint = hashlib.sha256(source.encode()).hexdigest()
    print(f"Actual Intent parser preserved metadata, roster and full prompt for {len(loaded)} specialists; source SHA-256 {fingerprint}")


if __name__ == "__main__":
    main()
