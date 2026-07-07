#!/usr/bin/env python3
"""Build the Cogscope public drift tracker static site.

Reads JSON records from tracker/data/ (samples + community), aggregates
per model, and writes tracker/site/index.html + tracker/site/data.js.

No network, no API keys, no build toolchain — run with plain Python 3.10+.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

TRACKER_ROOT = Path(__file__).resolve().parent
DATA_DIR = TRACKER_ROOT / "data"
SITE_DIR = TRACKER_ROOT / "site"
ANNOTATIONS_FILE = DATA_DIR / "annotations.json"


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


def render_html(by_model: dict, annotations: list[dict], record_count: int) -> str:
    """Generate index.html with Chart.js from CDN."""
    models_json = json.dumps(list(by_model.keys()))
    sample_count = sum(1 for recs in by_model.values() for r in recs if r.get("sample"))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Cogscope Drift Tracker</title>
  <link rel="stylesheet" href="style.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
</head>
<body>
  <header>
    <h1>Cogscope Drift Tracker</h1>
    <p class="tagline">Community-submitted behavioral fingerprints over time — not final answers, but how models reasoned.</p>
    <p class="meta">{record_count} records across {len(by_model)} model(s) · {sample_count} marked as sample/demo data</p>
  </header>

  <section class="notice">
    <strong>Sample data included.</strong> Records with <code>"sample": true</code> are demonstration
    data for the build pipeline — not live API measurements. Community submissions contain only
    numeric metrics; never prompts or outputs.
  </section>

  <section id="model-tabs" class="tabs"></section>
  <section class="chart-wrap">
    <canvas id="metrics-chart" height="120"></canvas>
  </section>
  <section class="legend">
    <h2>Metrics</h2>
    <ul>
      <li><span class="swatch depth"></span> Reasoning depth</li>
      <li><span class="swatch verify"></span> Verification steps</li>
      <li><span class="swatch hedge"></span> Hedging ratio</li>
      <li><span class="swatch drift"></span> Drift score vs submitter baseline</li>
    </ul>
  </section>
  <section id="annotations" class="annotations">
    <h2>Known model updates</h2>
    <p class="dim">Only verified, cited dates are shown. See <code>tracker/data/annotations.json</code> for TODOs.</p>
    <ul id="annotation-list"></ul>
  </section>
  <footer>
    <p>Built from opt-in <code>cogscope submit</code> data. <a href="https://github.com/aadi-joshi/cogscope">Source</a></p>
  </footer>
  <script src="data.js"></script>
  <script>
    const MODELS = {models_json};
    const ANNOTATIONS = {json.dumps(annotations)};
    // data.js sets window.TRACKER_DATA
    (function() {{
      const data = window.TRACKER_DATA || {{}};
      const tabs = document.getElementById('model-tabs');
      let active = MODELS[0] || null;
      let chart = null;

      function renderTabs() {{
        tabs.innerHTML = MODELS.map(m =>
          `<button type="button" class="tab${{m === active ? ' active' : ''}}" data-model="${{m}}">${{m}}</button>`
        ).join('');
        tabs.querySelectorAll('.tab').forEach(btn => {{
          btn.addEventListener('click', () => {{
            active = btn.dataset.model;
            renderTabs();
            renderChart();
          }});
        }});
      }}

      function renderChart() {{
        const recs = data[active] || [];
        const ctx = document.getElementById('metrics-chart');
        if (chart) chart.destroy();
        if (!recs.length) return;
        const labels = recs.map(r => r.timestamp);
        chart = new Chart(ctx, {{
          type: 'line',
          data: {{
            labels,
            datasets: [
              {{ label: 'Depth', data: recs.map(r => r.depth), borderColor: '#3b82f6', tension: 0.2, yAxisID: 'y' }},
              {{ label: 'Verification', data: recs.map(r => r.verification_steps), borderColor: '#22c55e', tension: 0.2, yAxisID: 'y' }},
              {{ label: 'Hedging', data: recs.map(r => r.hedging_ratio), borderColor: '#eab308', tension: 0.2, yAxisID: 'y1' }},
              {{ label: 'Drift', data: recs.map(r => r.drift_score), borderColor: '#ef4444', tension: 0.2, yAxisID: 'y1' }},
            ]
          }},
          options: {{
            responsive: true,
            interaction: {{ mode: 'index', intersect: false }},
            plugins: {{
              title: {{ display: true, text: active + (recs[0]?.sample ? ' (includes sample data)' : '') }}
            }},
            scales: {{
              x: {{ type: 'time', time: {{ unit: 'day' }} }},
              y: {{ position: 'left', title: {{ display: true, text: 'Count' }} }},
              y1: {{ position: 'right', grid: {{ drawOnChartArea: false }}, title: {{ display: true, text: 'Ratio / drift' }}, min: 0, max: 1 }}
            }}
          }}
        }});
      }}

      const annList = document.getElementById('annotation-list');
      if (ANNOTATIONS.length) {{
        annList.innerHTML = ANNOTATIONS.map(a =>
          `<li><strong>${{a.date}}</strong> — ${{a.label}}` +
          (a.source_url ? ` <a href="${{a.source_url}}">source</a>` : '') + `</li>`
        ).join('');
      }} else {{
        annList.innerHTML = '<li class="dim">No verified annotation dates yet — add cited entries to tracker/data/annotations.json</li>';
      }}

      renderTabs();
      renderChart();
    }})();
  </script>
</body>
</html>
"""


def write_data_js(by_model: dict) -> None:
    path = SITE_DIR / "data.js"
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.TRACKER_DATA = ")
        json.dump(by_model, f, indent=2)
        f.write(";\n")


def main() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    records = load_records()
    if not records:
        print("WARN: no records found — writing empty site")
    by_model = aggregate_by_model(records)
    annotations = load_annotations()
    html = render_html(by_model, annotations, len(records))
    index = SITE_DIR / "index.html"
    with open(index, "w", encoding="utf-8") as f:
        f.write(html)
    write_data_js(by_model)
    print(f"Built tracker site: {index}")
    print(f"  Models: {', '.join(by_model.keys()) or '(none)'}")
    print(f"  Records: {len(records)}")


if __name__ == "__main__":
    main()
