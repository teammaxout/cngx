# The Public Drift Log

!!! note "Advanced, experimental"
    The community tracker is an advanced, experimental feature tied to the drift engine, not the headline. It currently has little to no community data. Treat it as an early, mostly empty signal board, not a dataset you can draw conclusions from.

The **cngx Drift Tracker** is a static site showing behavioral fingerprint trends over time, built from opt-in community submissions.

- **Source:** `tracker/` in the repository
- **Live site:** [aadi-joshi.github.io/cngx](https://aadi-joshi.github.io/cngx/)
- **Live data:** aggregated metrics are served from a public S3 index (refreshed every few minutes in the browser)
- **Cost:** GitHub Pages for the static shell; a small AWS stack handles opt-in submissions

## Demo

See the live tracker: [aadi-joshi.github.io/cngx](https://aadi-joshi.github.io/cngx/)

## What it shows

Per-model timeline charts of:

- Reasoning depth
- Verification steps
- Hedging ratio
- Drift score (vs each submitter's own baseline)

Tabs are real provider model ids from opt-in submits (for example `gpt-4o-mini`). Harness names like `cngx-e2e-test` are rejected and never shown. Duplicate fingerprint shapes (same response under two baselines) are rejected so charts do not draw vertical spikes.

Sample data ships with `"sample": true` so the pipeline works with zero API spend. Real community records are opt-in submissions, and today there are few if any, so charts are largely empty until submits land. The public index is rate-limited but not cryptographically attested: treat it as a signal board, not a scientific dataset.

## How to contribute data

```bash
cngx pin --label my-baseline
cngx watch    # or capture traffic locally
cngx submit --baseline my-baseline --dry-run   # preview exact JSON
cngx submit --baseline my-baseline           # confirm to submit
```

You will see the full payload before anything is sent. It never includes prompt or output text.

After you confirm, `cngx submit` POSTs the JSON to a serverless endpoint. No GitHub account, no pull request, no API keys. No personal identity is collected or stored anywhere in the pipeline.

New records appear on the live tracker within a few minutes (browser cache is short).

Schema details: [tracker/README.md](https://github.com/aadi-joshi/cngx/blob/main/tracker/README.md)

## Optional maintainer probe

A separate workflow (`tracker-probe.yml`) can run a small API battery **only if** a repository admin sets `ENABLE_TRACKER_PROBE=true`. It is **off by default**, budget-capped at 5 calls/run, and costs real money if enabled. The tracker works fine without it.

## Build locally

```bash
python tracker/build.py
# open tracker/site/index.html
```

## Related

- [Proxy and Privacy](proxy-and-privacy.md)
- [CLI `submit`](../cli/reference.md#submit)
