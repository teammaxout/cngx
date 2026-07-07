# Quickstart

The fastest way to understand Cogscope is to install and run it:

```bash
pipx install cogscope
cogscope quickstart
```

**Requirements:** Python 3.10+ (for pipx/pip), **no API keys**, **no configuration**, **no Docker**.

## What you'll see

Terminal demo (recorded with [VHS](https://github.com/charmbracelet/vhs), mock adapter, no API keys):

![Cogscope quickstart demo](../assets/quickstart.gif)

The command runs a mock scenario in under 30 seconds:

1. **Without Cogscope**: a pipeline completes and downstream systems would run, but reasoning assumptions were violated (verification skipped, confidence too low).
2. **With Cogscope**: the same shallow behavior is **blocked** against a policy (reasoning depth too low, no verification steps detected).

The demo uses the mock adapter and a deterministic fingerprint so the BLOCKED result is reliable every run, not random LLM variance.

Regenerate the GIF after UI changes:

```bash
vhs scripts/demo/quickstart.tape
```

See `scripts/demo/README.md` for Windows ttyd notes and full instructions.

## Try a policy check yourself

After install, run a one-shot check with the bundled lenient policy:

```bash
cogscope check -c examples/contracts/basic_reasoning.yaml \
  "What is 2+2? Show your work." \
  --adapter mock --model mock-model
```

Expected result (verified):

```
Cogscope policy check
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
cogscope init --yes
cogscope status
```

Shows trace/fingerprint counts in your local `.cogscope/cogscope.db`.

## What to do next

| Goal | Command |
|------|---------|
| Run an agent through Cogscope (recommended) | `cogscope wrap -- aider` |
| Live dashboard while capturing | `cogscope watch` |
| Pin normal behavior | `cogscope pin --label baseline` |
| Session trajectory report | `cogscope report --session SESSION_ID` |
| Compare recent calls | `cogscope diff --baseline baseline` |
| Share anonymous metrics (opt-in) | `cogscope submit --baseline baseline --dry-run` |

See [Wrap your agent](../guides/wrap-agent.md) and the [CLI Reference](../cli/reference.md).
