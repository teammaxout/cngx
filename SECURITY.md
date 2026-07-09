# Security Policy

## Reporting a vulnerability

**Do not open a public GitHub issue for security bugs.**

Report vulnerabilities privately:

1. **TODO(human):** Add a dedicated security contact (e.g. `security@yourdomain.com`) or use [GitHub private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) for this repository.
2. Until that is configured, use the repository owner’s contact method listed on the GitHub org/profile page.
3. Include: description, steps to reproduce, affected versions, and impact.

We aim to acknowledge reports within **48 hours** and will coordinate disclosure before any public fix.

## What cngx does with secrets and data

cngx is **local-first**:

| Data | Behavior |
|------|----------|
| Provider API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, etc.) | Read from the environment for request forwarding only. Held **in memory** for the duration of a single proxied request. **Never logged, never persisted, never written to DuckDB.** |
| Captured traces and fingerprints | Stored locally under `.cngx/` (DuckDB). Stays on your machine unless you copy it elsewhere. |
| Telemetry | **None.** No phone-home, no usage analytics, no crash reporting to a vendor backend. |
| Outbound network (proxy) | Only traffic you initiate: forwarded requests to the LLM provider you configured. |

The only exception is **`cngx submit`**: optional sharing of allowlisted drift summaries to the community tracker, with an **explicit preview-and-confirm** step before anything is sent. Nothing is uploaded by default.

## Scope

**In scope**

- Local proxy mishandling API keys (logging, persistence, leakage to third parties)
- Path traversal or arbitrary file write via CLI/storage
- ReDoS or injection via user-supplied policy YAML regex patterns (`cngx/security/`)
- Sandbox escapes in any code-execution paths still present in the OSS tree

**Out of scope**

- Vulnerabilities in upstream LLM provider APIs
- Issues that require the reporter to already have full shell access on the machine running cngx
- Denial of service from intentionally flooding the local proxy on localhost

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |
| < 0.1   | No        |
