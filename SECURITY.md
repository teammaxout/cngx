# Security Policy

## Reporting a vulnerability

**Do not open a public GitHub issue for security bugs.**

Report vulnerabilities privately via [GitHub private vulnerability reporting](https://github.com/aadi-joshi/cngx/security/advisories/new) on this repository.

Include: description, steps to reproduce, affected versions, and impact.

We aim to acknowledge reports within **48 hours** and will coordinate disclosure before any public fix.

## What cngx does with secrets and data

cngx is **local-first**:

| Data | Behavior |
|------|----------|
| Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, etc.) | Read from the environment for request forwarding only. Held **in memory** for the duration of a single proxied request. **Never logged, never persisted, never written to DuckDB.** |
| Captured traces and fingerprints | Stored locally under `.cngx/` (DuckDB). Stays on your machine unless you copy it elsewhere. |
| Telemetry | **None.** No phone-home, no usage analytics, no crash reporting to a vendor backend. |
| Outbound network (proxy) | Only traffic you initiate: forwarded requests to the LLM provider you configured. |

The only exception is **`cngx submit`**: optional sharing of allowlisted drift summaries to the community tracker, with an **explicit preview-and-confirm** step before anything is sent. Nothing is uploaded by default. CDN/API access logs may still exist on the tracker infrastructure; the submit payload itself contains no prompts or outputs.

## Scope

**In scope**

- Local proxy mishandling API keys (logging, persistence, leakage to third parties)
- Path traversal or arbitrary file write via CLI/storage
- ReDoS or injection via user-supplied policy YAML regex patterns (`cngx/security/`)
- Sandbox escapes in any code-execution paths still present in the OSS tree

**Out of scope**

- Vulnerabilities in upstream LLM provider APIs
- Issues that require the reporter to already have full shell access on the machine running cngx
- Social engineering or physical access attacks

## Supported versions

Security fixes land on the latest `0.1.x` release on PyPI and GitHub Releases.
