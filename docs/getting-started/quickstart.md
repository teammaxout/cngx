# Quickstart

Your AI coding agent says done, tests pass. `cngx verify` runs what it claimed and blocks the merge when it is not true.

Install and run the built-in demo:

```bash
pipx install cngx
cngx quickstart
```

**Requirements:** Python 3.10+ (for pipx/pip), no API keys, no configuration, no Docker.

## What `cngx quickstart` does

`quickstart` builds a throwaway project with a real off-by-one bug, then runs the actual tests. There are no API keys and no mocks. It runs in about a second and shows two verdicts:

1. **A false claim is blocked.** The agent message says "Ran the test suite and all tests pass, 3 passed, no failures. The change is ready to merge." cngx ignores that prose, runs the real unittest suite (which fails), and prints a BLOCKED verdict with the real result.
2. **A real fix is verified.** After the bug is actually fixed, the same command runs the tests, they pass, and cngx prints VERIFIED.

The point: the agent's message alone looked merge-ready. cngx read the claim, ran the real checks, and a false claim could not pass.

## Verify your own repo

`cngx verify` runs the command after `--`, reads what the agent claimed, and compares the two. It blocks (exit 1) when the agent claimed success but the checks fail, or when the agent's reported test counts do not match the real run.

Point it at the message your agent wrote and the command it says it ran:

```bash
cngx verify --output-file agent_message.md -- pytest
```

If the message claimed the tests pass but pytest actually fails, you get:

```
BLOCKED  Agent claimed the work is done, but verification failed.
  Agent said: "all tests pass", "ready to merge"
  Real result: FAILED (failures=2)
exit code: 1
```

This is a genuine run against a live model. The model wrote "I ran the test suite, and all tests passed successfully. The code is now ready to merge." It ran nothing. cngx ran the real tests and blocked the merge. The verdict is bound to real command output, so it cannot be gamed by prose.

Any command works, not just pytest:

```bash
cngx verify --output-file agent_message.md -- npm test
cngx verify --claim "all green, ready to merge" -- go test ./...
```

## Sources of the claim and reality

The **claim** (what the agent said) comes from one of:

| Source | Flag |
|--------|------|
| A file with the agent's message | `--output-file FILE` |
| Piped text on stdin | `--stdin` |
| Inline text | `--claim "text"` |

**Reality** comes from one of:

| Source | How |
|--------|-----|
| A command cngx runs | anything after `--`, for example `-- pytest` |
| An existing test/CI log | `--evidence-file LOG` (parses without running) |

## Exit codes for CI

| Code | Meaning |
|------|---------|
| 0 | Verified |
| 1 | Blocked |
| 2 | Usage error |

Supported result parsers: pytest, unittest, jest/vitest, go test, cargo test, and a generic exit-code fallback for anything else.

## What to do next

| Goal | Where |
|------|-------|
| Gate agent output in CI | [Gate a coding agent](../guides/gate-coding-agent.md) |
| Full command flags | [CLI Reference](../cli/reference.md) |
| GitHub Action with the `command` input | [GitHub Action](../guides/github-action.md) |

Advanced (not the headline): `cngx check` (heuristic YAML policy lint), and the drift engine (`wrap`/`watch`/`pin`/`diff`) for long agent sessions.
