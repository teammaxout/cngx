# Quickstart

The fastest way to understand cngx is to install and run it:

```bash
pipx install cngx
cngx quickstart
```

**Requirements:** Python 3.10+ (for pipx/pip), **no API keys**, **no configuration**, **no Docker**.

## What you'll see

Terminal demo (recorded with [VHS](https://github.com/charmbracelet/vhs), mock adapter, no API keys):

![cngx quickstart demo](../assets/quickstart.svg)

The command runs a mock scenario in under 30 seconds:

1. **Without cngx**: a pipeline completes and downstream systems would run, but reasoning assumptions were violated (verification skipped, confidence too low).
2. **With cngx**: the same shallow behavior is **blocked** against a policy (reasoning depth too low, no verification steps detected).

The demo uses the mock adapter and a deterministic fingerprint so the BLOCKED result is reliable every run, not random LLM variance.

Regenerate the demo SVG after UI changes:

```bash
vhs scripts/demo/quickstart.tape
```

See `scripts/demo/README.md` for Windows ttyd notes and full instructions.

## Try a policy check yourself

After install, run a one-shot check with the bundled lenient policy:

```bash
cngx check -c examples/contracts/basic_reasoning.yaml \
  "What is 2+2? Show your work." \
  --adapter mock --model mock-model
```

Expected result (verified):

```
cngx policy check
Policy: basic_reasoning v1.0.0
STATUS: PASSED
EXIT CODE: 0
```

Exit codes for CI:

| Code | Meaning |
|------|---------|
| 0 | Passed |
| 1 | Blocked |
| 2 | Failed (review) |

## Initialize for local capture

```bash
cngx init --yes
cngx status
```

Shows trace/fingerprint counts in your local `.cngx/cngx.db`.

## What to do next

| Goal | Command |
|------|---------|
| Run an agent through cngx (recommended) | `cngx wrap -- aider` |
| Live dashboard while capturing | `cngx watch` |
| Pin normal behavior | `cngx pin --label baseline` |
| Session trajectory report | `cngx report --session SESSION_ID` |
| Compare recent calls | `cngx diff --baseline baseline` |
| Share opt-in metrics | `cngx submit --baseline baseline --dry-run` |

See [Wrap your agent](../guides/wrap-agent.md) and the [CLI Reference](../cli/reference.md).
