PYTHON ?= python3
NODE ?= node

.PHONY: build check test test-watchdog test-parser test-evals eval-actual

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

# Deterministic fake-service and oracle tests; no model or authentication.
test-evals:
	$(PYTHON) -S -m unittest discover -s tests -p test_evals.py -v

# Opt-in: consumes provider quota, using synthetic tools only.
eval-actual: check
	@test -n "$(EVAL_MODEL)" || { echo "Set EVAL_MODEL to an accessible Codex model ID"; exit 2; }
	$(PYTHON) -S -m evals.run --model "$(EVAL_MODEL)" $(EVAL_ARGS)
