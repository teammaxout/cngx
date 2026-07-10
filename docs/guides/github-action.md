# GitHub Action

cngx ships a reusable composite action at the repository root. It runs the real verification command your AI agent claimed it ran and fails the job when the claim is false.

## Minimal example (verify, recommended)

Set `command` to the real verification command and `output-file` to the agent's message. cngx runs the command, reads the claim, and blocks on a false claim. No API keys.

```yaml
name: Agent gate

on:
  pull_request:

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Your agent writes its merge-ready message to a file, for example:
      # - run: ./run-agent.sh > agent_message.md

      - uses: aadi-joshi/cngx@v0.2.0
        with:
          output-file: agent_message.md
          command: pytest -q
```

**Exit codes:** `0` verified, `1` blocked, `2` usage error. The job fails on a blocked verdict.

The `command` value can be any test or build command:

```yaml
      - uses: aadi-joshi/cngx@v0.2.0
        with:
          output-file: agent_message.md
          command: npm test
```

## Inputs (verify)

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `command` | one of `command` / `evidence-file` | | Verification command to run, for example `pytest -q`. This is the main path |
| `output-file` | no | | Path to the agent's message; cngx reads the verification claim from it |
| `evidence-file` | one of `command` / `evidence-file` | | Path to an existing test/CI log to gate offline instead of running a command |
| `require-claim` | no | `false` | Also block when checks pass but the agent made no verification claim |
| `timeout` | no | `600` | Seconds before the verification command is killed |
| `python-version` | no | `3.11` | Python version for `setup-python` |
| `cngx-version` | no | latest PyPI | Pin a release (for example `0.2.0`) |
| `install-mode` | no | `pypi` | `pypi` or `editable` (`pip install -e .`, for dogfooding) |
| `json-output` | no | `false` | Emit JSON results to stdout |

Provide either `command` (run it) or `evidence-file` (parse an existing log), not both.

## Offline: gate an existing CI log

When the tests already ran in a prior step, point the action at the log instead of running the command again:

```yaml
      - name: Run tests
        run: pytest -q | tee pytest.log

      - uses: aadi-joshi/cngx@v0.2.0
        with:
          output-file: agent_message.md
          evidence-file: pytest.log
```

cngx parses the log for a real result line and blocks when the agent's claim contradicts it.

## Require a verification claim

Block even when the checks pass, if the agent never actually claimed to verify:

```yaml
      - uses: aadi-joshi/cngx@v0.2.0
        with:
          output-file: agent_message.md
          command: pytest -q
          require-claim: "true"
```

## JSON output for downstream steps

```yaml
      - uses: aadi-joshi/cngx@v0.2.0
        id: cngx
        with:
          output-file: agent_message.md
          command: pytest -q
          json-output: "true"
```

## Advanced: legacy `check` (heuristic policy lint)

When neither `command` nor `evidence-file` is set, the action falls back to the legacy `cngx check`, which scores the *text* of agent output against a YAML policy using regex heuristics. It does not run anything, so a fabricated "all tests passed" claim can satisfy it. Prefer the `command` path above for real proof.

The legacy inputs (`policy`, `prompt`, `prompt-file`, `model`, `adapter`, `task-id`) still exist for this path:

```yaml
      - uses: aadi-joshi/cngx@v0.2.0
        with:
          policy: examples/contracts/coding_agent_verification.yaml
          prompt: "Fix the pagination bug and run tests before merge"
          output-file: agent_message.md
```

## Dogfooding in this repository

The cngx repo tests the action from the checkout root:

```yaml
      - uses: actions/checkout@v4
      - uses: ./
        with:
          install-mode: editable
          command: pytest -q tests/unit/test_verify_verdict.py
```

## Related

- [Gate a coding agent](gate-coding-agent.md)
- [CLI `verify`](../cli/reference.md#verify)
- [Badge snippet](badge.md)
