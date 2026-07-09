# The Public Drift Log

The **cngx Drift Tracker** is a static site showing behavioral fingerprint trends over time, built from opt-in community submissions.

- **Source:** `tracker/` in the repository
- **Live site:** [aadi-joshi.github.io/cngx](https://aadi-joshi.github.io/cngx/)
- **Live data:** aggregated metrics are served from a public S3 index (refreshed every few minutes in the browser)
- **Cost:** GitHub Pages for the static shell; a small AWS stack handles opt-in submissions

## Demo

![cngx drift tracker walkthrough](../assets/tracker-demo.gif)

[Full recording (MP4, 1280x720)](../assets/tracker-demo.mp4) · [Static screenshot](../assets/tracker-demo.png)

The GIF autoplays in GitHub READMEs; the MP4 is the full-quality version for docs and releases.

## What it shows

Per-model timeline charts of:

- Reasoning depth
- Verification steps
- Hedging ratio
- Drift score (vs each submitter's own baseline)

Sample data ships with `"sample": true` so the pipeline works with zero API spend. Community records are real opt-in submissions.

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

## Build and record locally

```bash
python tracker/build.py
# open tracker/site/index.html

# Regenerate demo assets for README/docs:
python scripts/demo/record_tracker.py
```

See `scripts/demo/README.md` for Playwright setup.

## Related

- [Proxy and Privacy](proxy-and-privacy.md)
- [CLI `submit`](../cli/reference.md#submit)
