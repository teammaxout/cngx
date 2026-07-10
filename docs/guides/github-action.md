# GitHub Action

cngx ships a reusable composite action at the repository root. Add a policy check to your CI with one step.

## Minimal example (live capture, mock adapter)

Copy a policy YAML into your repo (or vendor `examples/contracts/basic_reasoning.yaml` from cngx), then add a job:

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  reasoning-policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: cngx policy check
        uses: aadi-joshi/cngx@v0.1.4
        with:
          policy: policies/basic_reasoning.yaml
          prompt: "What is 15 * 7? Show your reasoning step by step."
```

**Exit codes:** `0` pass, `1` blocked, `2` failed (policy load or capture error). The job fails on blocked or failed checks.

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `policy` | yes | | Path to behavior policy YAML |
| `prompt` | live: one of `prompt` / `prompt-file`; offline: optional context | | Inline task text |
| `prompt-file` | live: one of `prompt` / `prompt-file`; offline: optional context | | Path to task context file |
| `output-file` | offline mode | | Path to agent output file (no LLM call, no API keys) |
| `python-version` | no | `3.11` | Python version for `setup-python` |
| `cngx-version` | no | latest PyPI | Pin a release (for example `0.1.0`) |
| `install-mode` | no | `pypi` | `pypi` or `editable` (`pip install -e .`, for dogfooding) |
| `model` | no | `mock-model` | Model name label stored on the trace |
| `adapter` | no | `mock` | `mock`, `openai`, `gemini`, or `claude` (online capture only) |
| `task-id` | no | `policy_check` | Task ID stored with the capture |
| `json-output` | no | `false` | Print JSON results |
| `init` | no | `true` | Run `cngx init --yes` first |

Provide **either** `output-file` (offline gate) **or** `prompt` / `prompt-file` (live capture).

## Gate agent output (no API keys)

Use this when your CI already has agent output on disk (patch summary, PR comment export, log file). cngx fingerprints the file and enforces your policy with zero provider calls.

```yaml
name: Agent CI

on:
  pull_request:

jobs:
  gate-agent-output:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # Your agent or script writes merge-ready text to a file:
      # - run: ./my-agent.sh --task "fix pagination" > agent_output.txt

      - name: cngx policy gate
        uses: aadi-joshi/cngx@v0.1.4
        with:
          policy: policies/coding_agent_verification.yaml
          prompt: "Fix the pagination bug and run tests before merge"
          output-file: agent_output.txt

      - name: cngx policy gate (prompt from file)
        uses: aadi-joshi/cngx@v0.1.4
        with:
          policy: policies/coding_agent_verification.yaml
          prompt-file: tasks/fix_pagination.txt
          output-file: agent_output.txt
          json-output: "true"
```

When `output-file` is set, the action skips adapter capture. No `OPENAI_API_KEY` or other provider secrets are required.

See `.github/workflows/example-agent-gate.yml` in this repo for a full dogfooding workflow that blocks `unverified_patch.txt` and passes `verified_fix.txt`.

## Long prompts (live capture)

```yaml
      - uses: aadi-joshi/cngx@v0.1.4
        with:
          policy: policies/basic_reasoning.yaml
          prompt-file: tests/fixtures/reasoning_prompt.txt
```

## Live model adapters

Set API keys on the job (never commit them). The action forwards them to `cngx check` only in live capture mode:

```yaml
  reasoning-policy:
    runs-on: ubuntu-latest
    env:
      OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - uses: aadi-joshi/cngx@v0.1.4
        with:
          policy: policies/basic_reasoning.yaml
          prompt: "Summarize this week's incident report with verification steps."
          adapter: openai
          model: gpt-4o-mini
```

## JSON output for downstream steps

```yaml
      - uses: aadi-joshi/cngx@v0.1.4
        id: cngx
        with:
          policy: policies/basic_reasoning.yaml
          prompt: "Explain how TCP handshakes work."
          json-output: "true"
```

## Dogfooding in this repository

The cngx repo tests the action from the checkout root:

```yaml
      - uses: actions/checkout@v4
      - uses: ./
        with:
          install-mode: editable
          policy: examples/contracts/basic_reasoning.yaml
          prompt: "What is 15 * 7? Show your reasoning step by step."
```

## Local smoke test

Approximate the composite steps on your machine:

```bash
python scripts/test_github_action_local.py
```

This runs editable install, live capture checks, offline `output-file` block and pass paths, matching `action.yml` logic.

## Related

- [Writing a Policy](../concepts/policies.md)
- [CLI `check`](../cli/reference.md#check)
- [Badge snippet](badge.md)
