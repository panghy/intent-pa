PYTHON ?= python3
NODE ?= node

.PHONY: build check test test-watchdog test-parser

build:
	$(PYTHON) -S scripts/build_pack.py

check:
	$(PYTHON) -S scripts/build_pack.py --check

test: check
	$(PYTHON) -S -m unittest discover -s tests -v
	$(MAKE) test-watchdog

test-watchdog:
	$(NODE) --test tests/test_watchdog.mjs

# Optional integration check: pass a local Intent specialists.rs source file.
# Compiles the actual parser functions in a disposable fixture, not the daemon.
test-parser: check
	@test -n "$(INTENT_SPECIALISTS_SOURCE)" || { echo 'Set INTENT_SPECIALISTS_SOURCE to the Intent specialist parser source file'; exit 1; }
	$(PYTHON) -S scripts/check_intent_parser.py --source "$(INTENT_SPECIALISTS_SOURCE)"
