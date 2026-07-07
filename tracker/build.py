#!/usr/bin/env python3
"""Build the Cogscope public drift tracker static site.

Reads JSON records from tracker/data/ (samples + community), aggregates
per model, and writes tracker/site/ (index.html, data.js, static assets).

No framework, plain Python 3.10+ and Chart.js from CDN.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

TRACKER_ROOT = Path(__file__).resolve().parent
DATA_DIR = TRACKER_ROOT / "data"
STATIC_DIR = TRACKER_ROOT / "static"
SITE_DIR = TRACKER_ROOT / "site"
ANNOTATIONS_FILE = DATA_DIR / "annotations.json"
GITHUB_REPO = "https://github.com/aadi-joshi/cogscope"


def load_records() -> list[dict]:
    """Load all JSON records from data/samples and data/community."""
    records: list[dict] = []
    for sub in ("samples", "community", "community/pending"):
        folder = DATA_DIR / sub
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json")):
            if path.name.startswith("."):
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except json.JSONDecodeError as e:
                print(f"WARN: skip {path}: {e}")
                continue
            if isinstance(data, list):
                records.extend(data)
            elif isinstance(data, dict) and "schema_version" in data:
                records.append(data)
            elif isinstance(data, dict) and "annotations" in data:
                continue
    return records


def load_annotations() -> list[dict]:
    """Load chart annotations; skip TODO placeholders without dates."""
    if not ANNOTATIONS_FILE.exists():
        return []
    with open(ANNOTATIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for ann in data.get("annotations", []):
        if ann.get("_todo") or not ann.get("date"):
            continue
        out.append(ann)
    return out


def aggregate_by_model(records: list[dict]) -> dict[str, list[dict]]:
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        model = r.get("model", "unknown")
        by_model[model].append(r)
    for model in by_model:
        by_model[model].sort(key=lambda x: x.get("timestamp", ""))
    return dict(by_model)


def count_samples(records: list[dict]) -> int:
    return sum(1 for r in records if r.get("sample"))


def render_html(
    by_model: dict,
    annotations: list[dict],
    record_count: int,
) -> str:
    """Generate index.html."""
    models = list(by_model.keys())
    sample_count = count_samples([r for recs in by_model.values() for r in recs])
    all_sample = sample_count == record_count and record_count > 0
    sample_badge = (
        '<span class="badge badge--sample">demonstration data only</span>' if all_sample else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Public, opt-in behavioral drift tracker for long autonomous agent sessions, community-submitted reasoning fingerprints over time.">
  <meta name="color-scheme" content="dark">
  <title>Cogscope Drift Tracker</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="style.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
</head>
<body>
  <div class="shell">
    <header class="site-header">
      <h1><span>&gt;</span> Cogscope Drift Tracker</h1>
      <p class="tagline">Community evidence of how agent reasoning behavior shifts over time, from opt-in session fingerprints, not vendor dashboards or one-off chatbot scores.</p>
      <div class="meta-row">
        <span>{record_count} record{"s" if record_count != 1 else ""} · {len(models)} model{"s" if len(models) != 1 else ""}</span>
        {sample_badge}
      </div>
    </header>

    <section class="explainer" aria-labelledby="what-heading">
      <h2 id="what-heading">What is this?</h2>
      <p><strong>Cogscope</strong> fingerprints how an autonomous agent <em>reasons</em> across long runs: depth, verification steps, hedging, not just final answer text. The tool watches for silent mid-session collapse (for example when verification stops varying) while each individual turn still looks fine. This page collects <strong>anonymous, numeric drift metrics</strong> submitted by users who pinned their own baselines.</p>
      <p>It is community evidence you can verify: no prompts, no outputs, only aggregated metrics from <code>cogscope submit</code>. A spike in drift score or a drop in verification steps is a signal worth investigating, not proof by itself.</p>
    </section>

    <section aria-labelledby="charts-heading">
      <h2 id="charts-heading">Metrics over time</h2>
      <p style="color: var(--text-muted); font-size: 0.875rem; margin: 0 0 1rem;">Select a model. Each chart uses its own scale, counts and ratios are never overlaid on one axis.</p>
      <div id="model-tabs" class="model-tabs" role="tablist" aria-label="Model filter"></div>
      <div class="chart-panel">
        <div class="chart-panel-header">
          <h3>Model: <span id="active-model-label">n/a</span></h3>
          <span id="model-badge" class="badge badge--sample">sample data</span>
        </div>
        <div class="chart-grid">
          <div class="chart-card">
            <h4>Reasoning depth <span>(steps)</span></h4>
            <div class="chart-wrap"><canvas id="chart-depth" role="img" aria-label="Reasoning depth over time"></canvas></div>
          </div>
          <div class="chart-card">
            <h4>Verification steps <span>(count)</span></h4>
            <div class="chart-wrap"><canvas id="chart-verification" role="img" aria-label="Verification steps over time"></canvas></div>
          </div>
          <div class="chart-card">
            <h4>Hedging ratio <span>(0 to 1)</span></h4>
            <div class="chart-wrap"><canvas id="chart-hedging" role="img" aria-label="Hedging ratio over time"></canvas></div>
          </div>
          <div class="chart-card">
            <h4>Drift score <span>(0 to 1 vs baseline)</span></h4>
            <div class="chart-wrap"><canvas id="chart-drift" role="img" aria-label="Drift score over time"></canvas></div>
          </div>
        </div>
        <div class="reading-guide">
          <strong style="color: var(--text);">How to read these charts</strong>
          <ul>
            <li><strong>Depth</strong> and <strong>verification</strong> are integer counts from regex/heuristic fingerprinting, higher usually means more explicit reasoning structure.</li>
            <li><strong>Hedging ratio</strong> measures uncertain vs confident language (0 to 1).</li>
            <li><strong>Drift score</strong> is relative to the submitter's own pinned baseline, not a universal benchmark.</li>
            <li>Yellow points indicate <strong>sample/demo</strong> records, not live API measurements.</li>
          </ul>
        </div>
      </div>
    </section>

    <section id="annotations-section" class="annotations-section hidden" aria-labelledby="annotations-heading">
      <h2 id="annotations-heading">Known model updates</h2>
      <ul id="annotation-list" class="annotations-list"></ul>
    </section>

    <section class="two-col" aria-labelledby="contribute-heading">
      <div>
        <h2 id="contribute-heading">Contribute your data</h2>
        <p style="color: var(--text-muted); font-size: 0.875rem;">Run Cogscope locally, pin a baseline, capture a long agent session, then submit anonymized metrics:</p>
        <div class="command-block">
          <span class="label">submit drift metrics</span>
          <pre>pipx install cogscope
cogscope init --yes
cogscope wrap -- aider     # or cogscope watch
cogscope pin --label my-baseline
cogscope submit --baseline my-baseline --dry-run
cogscope submit --baseline my-baseline</pre>
        </div>
        <p style="color: var(--text-dim); font-size: 0.8125rem;">Preview shows exact JSON before anything is sent. Only numeric metrics leave your machine.</p>
      </div>
      <div>
        <h2>Try Cogscope</h2>
        <p style="color: var(--text-muted); font-size: 0.875rem;">Zero API keys required for a first run:</p>
        <div class="command-block">
          <span class="label">install + quickstart</span>
          <pre>pip install cogscope
cogscope quickstart</pre>
        </div>
        <p style="color: var(--text-dim); font-size: 0.8125rem;">See the <a href="{GITHUB_REPO}">GitHub repo</a> for docs, proxy setup, and policy checks.</p>
      </div>
    </section>

    <footer class="site-footer">
      <p>Built from opt-in <code>cogscope submit</code> data. Metrics only, never prompts or model outputs.</p>
      <p><a href="{GITHUB_REPO}">github.com/aadi-joshi/cogscope</a> · <a href="https://aadi-joshi.github.io/cogscope/">This tracker</a></p>
    </footer>
  </div>
  <script src="data.js"></script>
  <script src="app.js"></script>
</body>
</html>
"""


def write_data_js(by_model: dict, annotations: list[dict]) -> None:
    path = SITE_DIR / "data.js"
    meta = {
        "models": list(by_model.keys()),
        "annotations": annotations,
        "record_count": sum(len(v) for v in by_model.values()),
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.TRACKER_DATA = ")
        json.dump(by_model, f, indent=2)
        f.write(";\nwindow.TRACKER_META = ")
        json.dump(meta, f, indent=2)
        f.write(";\n")


def copy_static_assets() -> None:
    """Copy hand-written CSS/JS into site output."""
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    if STATIC_DIR.is_dir():
        for name in ("style.css", "app.js"):
            src = STATIC_DIR / name
            if src.exists():
                shutil.copy2(src, SITE_DIR / name)


def main() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    records = load_records()
    if not records:
        print("WARN: no records found, writing empty site")
    by_model = aggregate_by_model(records)
    annotations = load_annotations()
    copy_static_assets()
    html = render_html(by_model, annotations, len(records))
    index = SITE_DIR / "index.html"
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)
    write_data_js(by_model, annotations)
    print(f"Built tracker site: {index}")
    print(f"  Models: {', '.join(by_model.keys()) or '(none)'}")
    print(f"  Records: {len(records)}")
    print(f"  Annotations (active): {len(annotations)}")


if __name__ == "__main__":
    main()
