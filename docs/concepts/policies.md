# Writing a Policy

A **policy** is a YAML file that defines behavioral requirements for an LLM response. cngx loads policies from disk and checks fingerprints against them.

!!! note "Internal name"
    The Python module is still called `contracts/` for historical reasons. In all user-facing commands and docs, we say **policy**.

## Minimal example

From `examples/contracts/basic_reasoning.yaml` (verified with `cngx check`):

```yaml
name: basic_reasoning
version: "1.0.0"
description: Minimum viable reasoning standards.

depth:
  min: 1
  severity: fail

steps:
  min: 1
  severity: fail

output:
  min_length: 20
  severity: fail

fail_on_violation: true
```

Run it:

```bash
cngx check -c examples/contracts/basic_reasoning.yaml \
  "What is 2+2?" --adapter mock
```

## Policy schema

Top-level fields on `BehaviorContract` (`cngx/contracts/schema.py`):

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | **Required.** Unique policy identifier |
| `version` | string | Semantic version (default `1.0.0`) |
| `description` | string | Human-readable summary |
| `domain` | enum | `math`, `research`, `code`, `logic`, `general`, `safety_critical` |
| `intent` | string | High-level goal |
| `task_ids` | list | Apply only to these task IDs (optional) |
| `models` | list | Apply only to these models (optional) |
| `depth` | object | `min`, `max`, `severity` |
| `steps` | object | `min`, `max`, `severity` |
| `verification` | object | `required`, `min_steps`, `severity` |
| `tools` | object | `required`, `forbidden`, `max_calls`, `min_diversity`, `severity` |
| `uncertainty` | object | `max_hedging_ratio`, `min_confidence_markers`, `max_uncertainty_markers`, `severity` |
| `output` | object | `min_length`, `max_length`, `require_structured`, `severity` |
| `forbidden_patterns` | list | Regex patterns that must not appear |
| `required_patterns` | list | Regex patterns that must appear |
| `block_on_violation` | bool | Block on any `block`-severity violation (default `true`) |

### Severity levels

| Value | Effect | Typical use |
|-------|--------|-------------|
| `warn` | Log only | Informational |
| `fail` | Violation, overridable | Important but flexible |
| `block` | Hard stop, exit code 1 | Critical invariants |

### Verification block

For math or safety-critical tasks (`examples/contracts/math_reasoning.yaml`):

```yaml
verification:
  required: true
  min_steps: 1
  severity: fail
```

This checks the `verification_steps` fingerprint metric (regex-detected), not semantic correctness.

### Pattern rules

```yaml
forbidden_patterns:
  - pattern: "I don't know"
    description: Model must attempt an answer
    check_output: true
    severity: block

required_patterns:
  - pattern: '\d+'
    description: Must contain numbers
    check_output: true
    severity: fail
```

Patterns run through a ReDoS-safe sandbox (`cngx/security/`).

## CI usage

```bash
cngx check -c examples/contracts/basic_reasoning.yaml "Your prompt here" --adapter mock
echo $?   # 0 pass, 1 blocked, 2 failed
```

GitHub Actions example: `.github/workflows/cngx-check.yml` in the repository.

## Bundled examples

| File | Strictness |
|------|------------|
| `examples/contracts/basic_reasoning.yaml` | Lenient |
| `examples/contracts/math_reasoning.yaml` | Requires verification |
| `examples/contracts/strict_verification.yaml` | Stricter verification |
| `examples/contracts/legacy/math_correctness.yaml` | Older production-style math policy |

## Related

- [CLI `check` command](../cli/reference.md#check)
- [Fingerprinting](fingerprinting.md), what metrics policies evaluate
