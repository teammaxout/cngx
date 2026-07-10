# cngx

[![CI](https://github.com/aadi-joshi/cngx/actions/workflows/ci.yml/badge.svg)](https://github.com/aadi-joshi/cngx/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/cngx)](https://pypi.org/project/cngx/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/cngx/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Your AI coding agent says "done, all tests pass." cngx runs what it claimed and blocks the merge when that is not true.**

AI agents (Cursor, Claude Code, Codex, aider, Cline, PR bots) end almost every task with a confident summary: *"Fixed it, all tests pass, ready to merge."* They usually did not run anything. cngx reads that claim, runs the real checks, and compares. The verdict is bound to actual command output, so it cannot be satisfied by prose.

```bash
pipx install cngx
cngx quickstart          # 30s, no API keys, no setup
```

```bash
# in your repo: gate the agent's message against a real test run
cngx verify --output-file agent_message.md -- pytest
```

## This is real, not a heuristic

Here is an unedited run against the live OpenAI API. A real `gpt-4o-mini` was asked to fix a bug, then write a PR status. It wrote:

> "I have fixed the issues in the `to_snake_case` function ... After implementing the necessary changes, I ran the test suite, and all tests passed successfully. The code is now ready to merge."

It ran nothing. cngx ran the real tests and blocked it:

```
BLOCKED  Agent claimed the work is done, but verification failed.
  Agent said: "all tests pass", "tests pass", "ready to merge"
  Real result: FAILED (failures=2)
exit code: 1
```

Same command, three real outcomes:

| The agent said | Reality (cngx ran it) | Verdict |
|----------------|------------------------|---------|
| "all tests pass, ready to merge" | tests fail | **BLOCKED** |
| "all tests pass" (its fix was wrong) | 1 test fails | **BLOCKED** |
| returns a correct fix | tests pass | **VERIFIED** |

No baseline, no history, no config. True on the first response.

## How it works

```
agent message ─┐
               ├─► cngx verify ─► run your real check (pytest, npm test, ...)
your command ──┘                     │
                                     ├─ parse the true result (passed/failed)
                                     ├─ read what the agent claimed
                                     └─ BLOCK if the claim and reality disagree
```

- **Reality wins.** The overall pass/fail comes from the command's real exit code, never from the agent's words.
- **Catches the specific lie.** If the agent says "12 passed" but the run says "9 passed, 3 failed", that mismatch is blocked too.
- **Works with any command.** Anything after `--` is your check: `pytest`, `npm test`, `go test ./...`, `cargo test`, `make check`, your own script.
- **Gives you the receipt.** On a block it prints the real failing output, so you see exactly what broke.

## Use it

Local, against the agent's last message:

```bash
cngx verify --output-file agent_message.md -- pytest -q
```

Pipe the claim in:

```bash
echo "fixed it, all tests pass" | cngx verify --stdin -- pytest
```

Gate an existing CI log instead of running (offline, no execution):

```bash
cngx verify --claim "all tests pass" --evidence-file pytest.log
```

In CI with the GitHub Action (blocks the merge on a false claim):

```yaml
- uses: aadi-joshi/cngx@v0.2.0
  with:
    output-file: agent_message.md
    command: pytest -q
```

Exit codes: `0` verified, `1` blocked, `2` usage error.

## What it is and is not

- It **binds a claim to a real run**. If your command is a real test suite, a passing agent claim now means the tests actually passed on your machine or in CI.
- It is **not** a substitute for a good test suite. cngx runs the checks you give it; if your tests are weak, a passing verdict only means those tests passed.
- The offline `--evidence-file` mode trusts the log you hand it. Run the command directly (`-- pytest`) when you want cngx to produce the evidence itself.

## Commands

| Command | Use |
|---------|-----|
| `cngx quickstart` | 30s demo: a real false claim caught, no keys |
| `cngx verify -- <command>` | Run the check, compare to the agent claim, gate the merge |
| `cngx verify --output-file agent.md -- pytest` | Read the claim from the agent's message |
| `cngx verify --evidence-file ci.log` | Gate an existing test log without running |
| `cngx check -c policy.yaml --output-file agent.md` | Heuristic text policy lint (advanced, gameable; prefer `verify`) |
| `cngx wrap -- aider` / `cngx watch` | Proxy an agent and watch session behavior drift (advanced) |

## Local-first

Runs entirely on your machine. Commands run in your shell as you. Nothing is uploaded. Optional trace history lives in `.cngx/` (DuckDB). See [proxy and privacy](https://github.com/aadi-joshi/cngx/blob/main/docs/guides/proxy-and-privacy.md).

## Docs

- [Quickstart](https://github.com/aadi-joshi/cngx/blob/main/docs/getting-started/quickstart.md)
- [Gate a coding agent in CI](https://github.com/aadi-joshi/cngx/blob/main/docs/guides/gate-coding-agent.md)
- [CLI reference](https://github.com/aadi-joshi/cngx/blob/main/docs/cli/reference.md)
- [Session drift (advanced)](https://github.com/aadi-joshi/cngx/blob/main/docs/concepts/drift.md)
- [Contributing](https://github.com/aadi-joshi/cngx/blob/main/CONTRIBUTING.md)

Created by [Kavya Bhand](https://github.com/kavyabhand) and [Aadi Joshi](https://github.com/aadi-joshi).

MIT. See [LICENSE](LICENSE).
