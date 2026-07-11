# Coding agent verification recipes

These recipes save an agent's final message, run the check it claimed to run, and use the `cngx verify` exit code as the gate. Exit code 0 is verified; exit code 1 is blocked.

## Claude Code

Ask Claude Code to write its final summary to `agent.md`, then run:

```bash
cngx verify --output-file agent.md -- pytest -q
```

Expected result: `VERIFIED` when the real tests match the claim, or `BLOCKED` when they fail or the reported counts disagree.

## Cursor

Save Cursor's final chat response as `agent.md`, then run the project check:

```bash
cngx verify --output-file agent.md -- npm test
```

Expected result: `VERIFIED` with exit 0, or `BLOCKED` with exit 1. The prose in `agent.md` cannot make a failing command pass.

## Codex

Have Codex include its verification result in `agent.md`, then execute the same command independently:

```bash
cngx verify --output-file agent.md -- python -m unittest
```

Expected result: `VERIFIED` when the command succeeds and supports the claim; otherwise `BLOCKED`.

## aider

Copy aider's last assistant message and pipe it directly to cngx:

```bash
printf '%s\n' 'Fixed the parser; all tests pass.' |
  cngx verify --stdin -- pytest -q
```

Expected result: `VERIFIED` only when pytest confirms the piped claim, or `BLOCKED` when reality differs.

## Pull request and merge bots

Save the bot's final claim as `agent.md`, then make verification a required GitHub Actions job:

```yaml
- uses: actions/checkout@v4
- uses: aadi-joshi/cngx@v0.2.0
  with:
    output-file: agent.md
    command: pytest -q
```

A `VERIFIED` result keeps the job green. A `BLOCKED` result fails the job and prevents auto-merge when the job is configured as a required check.

## Notes

- Generate `agent.md` in an earlier step; do not replace it with a hand-written success claim.
- Use `--require-claim` when silence about verification should also block the merge.
- For checks already run in CI, use `--evidence-file test.log` instead of running the command again.

See [Gate a coding agent](gate-coding-agent.md) for the full trust model and [GitHub Action](github-action.md) for all Action inputs.
