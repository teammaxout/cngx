# Session-level trajectory tracking

Long-running agent sessions can degrade in ways that **single-response fingerprinting cannot see**. Each turn may look normal while the session as a whole quietly loses varied verification behavior, sometimes called hollow verbosity: repetitive output with a flat, unverified pattern.

Cogscope tracks multi-turn sessions so you can spot this trajectory-level pattern, separate from per-turn structural drift alerts.

## What gets tracked

When you run `cogscope watch`:

- Pass an explicit id: `cogscope watch --session-id my-agent-run`
- Or let Cogscope infer one from request headers (`X-Session-Id`, `X-Conversation-Id`, etc.), body metadata (`session_id`, `conversation_id`), or a stable hash of the message history prefix

Each proxied call is stored in DuckDB with:

| Field | Meaning |
|-------|---------|
| `session_id` | Conversation/session identifier |
| `session_turn` | 1-based turn number within that session |

## Session stability warning (not structural drift)

Per-turn alerts compare one response to your pinned baseline. **Session stability warnings** compare the *sequence* of verification behavior across turns within one session.

### Concrete detection rule

After at least **20 turns**, Cogscope compares:

1. **Baseline window** (turns 1-10): `verification_steps` variance must be at least **0.5** and mean at least **2.0** (session started with varied, meaningful verification).
2. **Recent window** (last 10 turns): variance must be at most **0.15**, mean at most **1.0**, and at most **2** distinct values (verification flattened to a constant low pattern).

If both hold, Cogscope raises a **session stability warning**. This is labeled differently from structural drift on purpose.

Constants live in `cogscope/drift/trajectory.py` (`TrajectoryCollapseConfig`).

## What this does and does not mean

| Does | Does not |
|------|----------|
| Flag when verification behavior stops varying across many turns | Prove the model became less capable |
| Help you investigate long autonomous runs | Replace human review of agent output |
| Complement per-turn structural drift | Catch every failure mode |

Provider system-prompt changes, task switches, or intentional conciseness can also flatten metrics. Treat warnings as "something changed across the session, go look."

## CLI

```bash
# Track a named session
cogscope watch --session-id coding-agent-run-42

# After or during a session
cogscope report --session coding-agent-run-42
```

The live TUI shows session turn count and a verification health indicator (`warming up`, `varied`, `flattening`, `collapsed`).

## Honest limits

- Metrics are still regex/heuristic counts on surface text.
- The rule targets verification-step collapse specifically; other failure modes may not trigger.
- Auto-detected session ids from message hashes can split or merge conversations if history editing changes the prefix.

This is a **heuristic pattern check on a real and important failure mode**, not a proven diagnosis.
