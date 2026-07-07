# The Public Drift Log

The **Cogscope Drift Tracker** is a static site showing behavioral fingerprint trends over time, built from opt-in community submissions.

- **Source:** `tracker/` in the repository
- **Live site:** [aadi-joshi.github.io/cogscope](https://aadi-joshi.github.io/cogscope/)
- **Cost:** $0 (GitHub Actions + Pages on a public repo)

## Demo

![Cogscope drift tracker walkthrough](../assets/tracker-demo.gif)

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
cogscope pin --label my-baseline
cogscope watch    # or capture traffic locally
cogscope submit --baseline my-baseline --dry-run   # preview exact JSON
cogscope submit --baseline my-baseline           # confirm to submit
```

You will see the full payload before anything is sent. It never includes prompt or output text.

Records land in `tracker/data/community/` via pull request (or `pending/` for manual submission).

Schema details: [tracker/README.md](https://github.com/aadi-joshi/cogscope/blob/main/tracker/README.md)

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
