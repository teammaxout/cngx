#!/usr/bin/env python3
"""Build the cngx drift tracker static site.

Outputs tracker/site/ with index.html, docs/index.html, data.js, and static assets.
Charts load live community metrics from the S3 index in the browser.
"""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

TRACKER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = TRACKER_ROOT.parent
DATA_DIR = TRACKER_ROOT / "data"
STATIC_DIR = TRACKER_ROOT / "static"
ASSETS_DIR = REPO_ROOT / "docs" / "assets"
SITE_DIR = TRACKER_ROOT / "site"
ANNOTATIONS_FILE = DATA_DIR / "annotations.json"
GITHUB_REPO = "https://github.com/aadi-joshi/cngx"
PUBLIC_ENDPOINTS_FILE = TRACKER_ROOT / "public_endpoints.json"


def _tracker_live_index_url() -> str:
    if PUBLIC_ENDPOINTS_FILE.is_file():
        with open(PUBLIC_ENDPOINTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        url = data.get("tracker_index_url", "")
        if url and "PLACEHOLDER" not in url:
            return str(url)
    try:
        from cngx.tracker_endpoints import tracker_index_url

        url = tracker_index_url()
        if url and "PLACEHOLDER" not in url:
            return url
    except Exception:
        pass
    return ""


# Browser loads community metrics from the live S3 index; embedded data.js is a stale fallback only.
LIVE_DATA_POLICY = "s3_index_on_load"


def load_json_records(folder: Path) -> list[dict]:
    records: list[dict] = []
    if not folder.is_dir():
        return records
    for path in sorted(folder.glob("*.json")):
        if path.name.startswith("."):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            print(f"WARN: skip {path}: {exc}")
            continue
        if isinstance(data, list):
            records.extend(data)
        elif isinstance(data, dict) and "schema_version" in data:
            records.append(data)
    return records


def load_community_records() -> list[dict]:
    records: list[dict] = []
    for sub in ("community", "community/pending"):
        records.extend(load_json_records(DATA_DIR / sub))
    return [r for r in records if not r.get("sample")]


def load_sample_records() -> list[dict]:
    return load_json_records(DATA_DIR / "samples")


def load_annotations() -> list[dict]:
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
    for record in records:
        by_model[record.get("model", "unknown")].append(record)
    for model in by_model:
        by_model[model].sort(key=lambda x: x.get("timestamp", ""))
    return dict(by_model)


def _head(title: str, description: str, *, docs: bool = False) -> str:
    css = "../site.css" if docs else "site.css"
    icon = "../logo-light.svg" if docs else "logo-light.svg"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{description}">
  <meta name="color-scheme" content="dark">
  <title>{title}</title>
  <link rel="icon" href="{icon}" type="image/svg+xml">
  <link rel="stylesheet" href="{css}">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
</head>"""


def _topbar(*, docs: bool = False) -> str:
    home = "../" if docs else "./"
    docs_href = "./" if docs else "docs/"
    logo = "../logo-light.svg" if docs else "logo-light.svg"
    tracker_current = ' aria-current="page"' if not docs else ""
    docs_current = ' aria-current="page"' if docs else ""
    return f"""<header class="topbar">
  <a class="topbar-brand" href="{home}">
    <img class="topbar-logo" src="{logo}" alt="" width="36" height="22">
    <span>cngx</span>
  </a>
  <nav class="topbar-nav" aria-label="Site">
    <a href="{home}"{tracker_current}>tracker</a>
    <a href="{docs_href}"{docs_current}>docs</a>
    <a href="{GITHUB_REPO}">github</a>
  </nav>
</header>"""


def render_index(community_count: int) -> str:
    return (
        _head(
            "cngx Drift Tracker",
            "cngx checks whether a coding agent ran the verification your policy requires. "
            "Live opt-in drift metrics from cngx submit.",
        )
        + f"""
<body>
{_topbar()}
  <main class="page">
    <h1 class="page-title">cngx</h1>
    <p class="tagline">cngx checks whether a coding agent actually ran the verification your policy requires before you trust its output.</p>

    <div class="cmd-block">
      <span class="cmd-label">install</span>
      <pre>pipx install cngx
cngx quickstart</pre>
    </div>

    <p class="intro">This tracker plots opt-in drift metrics from <code>cngx submit</code>. Each point is numeric fingerprint data (depth, verification steps, hedging, drift vs the submitter's own baseline). No prompts, no outputs, no personal identity collected or stored by the submit API.</p>

    <section class="section" aria-labelledby="charts-heading">
      <h2 id="charts-heading">community drift metrics</h2>

      <div class="chart-intro">
        <p><strong>What you are looking at:</strong> how agents behave over time on real workloads, as reported by people who chose to share metrics.</p>
        <ul>
          <li><strong>verification steps</strong> drops can mean the agent stopped checking its work (the failure mode <code>cngx check</code> catches on a single response).</li>
          <li><strong>drift score</strong> rises when fingerprint shape diverges from that submitter's pinned baseline.</li>
          <li>A spike is a signal to investigate, not proof of regression.</li>
        </ul>
        <p class="status-line">live submissions: <strong id="community-status">...</strong><span id="index-updated-wrap" class="status-muted"></span></p>
      </div>

      <div id="loading-state" class="loading-panel" role="status">
        <p>Loading live index from S3...</p>
      </div>

      <div id="empty-state" class="empty-panel hidden">
        <p><strong>No submissions yet.</strong> Charts appear here after someone runs <code>cngx submit</code> and confirms the preview. We show this empty state rather than synthetic demo data.</p>
        <div class="cmd-block">
          <span class="cmd-label">be first</span>
          <pre>pipx install cngx
cngx init --yes
cngx wrap -- aider
cngx pin --label my-baseline
cngx submit --baseline my-baseline --dry-run
cngx submit --baseline my-baseline</pre>
        </div>
        <p><a class="btn" href="docs/#submit">how submit works</a></p>
      </div>

      <div id="chart-section" class="chart-panel hidden">
        <div class="chart-meta">
          <span>model: <strong id="active-model-label">none</strong></span>
          <span>source: <strong>live S3 index</strong></span>
        </div>
        <div id="model-tabs" class="chart-controls" role="tablist" aria-label="Model filter"></div>
        <div class="chart-grid">
          <div class="chart-card">
            <h3>reasoning depth</h3>
            <div class="chart-wrap"><canvas id="chart-depth" role="img" aria-label="Reasoning depth over time"></canvas></div>
          </div>
          <div class="chart-card">
            <h3>verification steps</h3>
            <div class="chart-wrap"><canvas id="chart-verification" role="img" aria-label="Verification steps over time"></canvas></div>
          </div>
          <div class="chart-card">
            <h3>hedging ratio</h3>
            <div class="chart-wrap"><canvas id="chart-hedging" role="img" aria-label="Hedging ratio over time"></canvas></div>
          </div>
          <div class="chart-card">
            <h3>drift score</h3>
            <div class="chart-wrap"><canvas id="chart-drift" role="img" aria-label="Drift score over time"></canvas></div>
          </div>
        </div>
      </div>
    </section>

    <section id="annotations-section" class="section hidden" aria-labelledby="annotations-heading">
      <h2 id="annotations-heading">known model updates</h2>
      <ul id="annotation-list"></ul>
    </section>

    <section class="section" aria-labelledby="privacy-heading">
      <h2 id="privacy-heading">privacy</h2>
      <p class="privacy-note">Submissions are opt-in. The API accepts only allowlisted numeric fields after you preview and confirm. Lambda does not log your IP or request headers; stored objects contain payload fields only. The aggregated index at <code>community/index.json</code> is world-readable so this page can load it without a rebuild.</p>
    </section>

    <footer class="site-footer">
      <p>metrics only. never prompts or model outputs.</p>
      <p><a href="{GITHUB_REPO}">source</a> · <a href="docs/">docs</a></p>
    </footer>
  </main>
  <script src="data.js"></script>
  <script src="app.js"></script>
</body>
</html>
"""
    )


def _copy_block(label: str, code: str) -> str:
    return f"""<div class="copy-wrap">
  <button type="button" class="copy-btn" aria-label="Copy code">copy</button>
  <pre>{code}</pre>
</div>"""


def render_docs() -> str:
    blocks = {
        "pipx": _copy_block("pipx", "pipx install cngx\ncngx version"),
        "quickstart": _copy_block("quickstart", "cngx quickstart"),
        "wrap": _copy_block(
            "wrap",
            "cngx wrap -- aider\ncngx wrap --session-id long-run -- python my_agent.py",
        ),
        "session": _copy_block("session report", "cngx report --session my-long-run"),
        "submit": _copy_block(
            "submit",
            "cngx submit --baseline my-baseline --dry-run\ncngx submit --baseline my-baseline",
        ),
    }
    return (
        _head(
            "cngx Docs",
            "Installation, CLI, drift detection, wrap, and submit for cngx.",
            docs=True,
        )
        + f"""
<body>
{_topbar(docs=True)}
  <div class="docs-layout">
    <aside class="docs-sidebar" aria-label="Documentation sections">
      <h2>sections</h2>
      <ul>
        <li><a href="#overview">overview</a></li>
        <li><a href="#install">install</a></li>
        <li><a href="#quickstart">quickstart</a></li>
        <li><a href="#gate-agent">gate agent output</a></li>
        <li><a href="#wrap">wrap</a></li>
        <li><a href="#watch">watch and sessions</a></li>
        <li><a href="#drift">drift detection</a></li>
        <li><a href="#cli">cli reference</a></li>
        <li><a href="#submit">submit and privacy</a></li>
        <li><a href="#schema">tracker schema</a></li>
      </ul>
    </aside>
    <main class="docs-content">
      <h1>cngx documentation</h1>
      <p>Local CLI that fingerprints coding-agent output and gates merges when verification is missing. Also proxies long agent sessions for baseline-relative drift. No cloud account required.</p>

      <h2 id="overview">overview</h2>
      <p>Day-one use: <code>cngx check --output-file</code> gates agent text in CI with no API keys. Longer runs: wrap the agent, pin a baseline, and watch for mid-session verification collapse.</p>
      <p>Install with pipx, gate offline or run agents through <code>cngx wrap</code>, optionally submit opt-in metrics to this tracker.</p>

      <h2 id="install">install</h2>
      <p><strong>Recommended:</strong> pipx puts <code>cngx</code> on your PATH in an isolated environment. No virtualenv to manage.</p>
      {blocks["pipx"]}
      <p><strong>Alternative:</strong> <code>pip install cngx</code> inside a project virtualenv.</p>
      <p><strong>No Python:</strong> standalone binaries on <a href="{GITHUB_REPO}/releases">GitHub Releases</a> (PyInstaller builds per platform).</p>
      <p>Docker is optional for containerizing the proxy on a server. It is not required for normal CLI use.</p>

      <h2 id="quickstart">quickstart</h2>
      <p>Zero API keys. Mock adapter demo in under 30 seconds.</p>
      {blocks["quickstart"]}

      <h2 id="gate-agent">gate agent output</h2>
      <p>Gate existing agent text in CI with no API keys: <code>cngx check --output-file output.txt -c policy.yaml</code>. Full walkthrough: <a href="{GITHUB_REPO}/blob/main/docs/guides/gate-coding-agent.md">docs/guides/gate-coding-agent.md</a></p>

      <h2 id="wrap">wrap</h2>
      <p>Zero-code instrumentation for existing agent CLIs. Starts the local proxy if needed and injects SDK base URL environment variables into the child process.</p>
      {blocks["wrap"]}
      <table class="docs-table">
        <thead><tr><th>Variable</th><th>Set to</th><th>Used by</th></tr></thead>
        <tbody>
          <tr><td><code>OPENAI_BASE_URL</code></td><td><code>http://127.0.0.1:8642/v1</code></td><td>OpenAI SDK, many compatible tools</td></tr>
          <tr><td><code>OPENAI_API_BASE</code></td><td>same</td><td>legacy alias in some agent wrappers</td></tr>
          <tr><td><code>ANTHROPIC_BASE_URL</code></td><td><code>http://127.0.0.1:8642</code></td><td>Anthropic SDK, Claude Code-style CLIs</td></tr>
        </tbody>
      </table>
      <p>Manual base URL configuration remains for tools that ignore environment overrides.</p>

      <h2 id="watch">watch and sessions</h2>
      <p><code>cngx watch</code> runs the proxy with a live terminal dashboard. Each turn gets a session id and turn number.</p>
      <p>After 20+ turns, cngx can raise a <strong>session stability warning</strong> when verification-step variance collapses (distinct from per-turn structural drift). See session thresholds in the repository docs under <code>docs/concepts/sessions.md</code>.</p>
      {blocks["session"]}

      <h2 id="drift">drift detection</h2>
      <p><strong>Structural drift</strong> compares heuristic fingerprint metrics (depth, verification steps, hedging, corrections) to your pinned baseline. Live proxy uses KSWIN and MDDM streaming tests; batch paths use Mann-Whitney U with Benjamini-Hochberg FDR and the Cauchy Combination Test (CCT).</p>
      <p><strong>Semantic drift</strong> (optional, <code>watch --semantic</code>) uses local embeddings. Neither structural nor semantic drift alone proves the model got worse.</p>
      <p>Alerts require corroboration across multiple metrics. Length-only shifts do not alert alone.</p>

      <h2 id="cli">cli reference</h2>
      <table class="docs-table">
        <thead><tr><th>Command</th><th>Purpose</th></tr></thead>
        <tbody>
          <tr><td><code>cngx init --yes</code></td><td>Create <code>.cngx/</code> local database</td></tr>
          <tr><td><code>cngx quickstart</code></td><td>Mock demo, no API keys</td></tr>
          <tr><td><code>cngx wrap -- &lt;cmd&gt;</code></td><td>Run agent through proxy (recommended)</td></tr>
          <tr><td><code>cngx watch</code></td><td>Proxy + live TUI dashboard</td></tr>
          <tr><td><code>cngx pin --label NAME</code></td><td>Pin baseline fingerprint</td></tr>
          <tr><td><code>cngx diff --baseline NAME</code></td><td>Compare recent traffic to baseline</td></tr>
          <tr><td><code>cngx check -c POLICY.yaml "prompt"</code></td><td>CI policy check (exit 0/1/2)</td></tr>
          <tr><td><code>cngx report --session ID</code></td><td>Session trajectory summary</td></tr>
          <tr><td><code>cngx submit --baseline NAME</code></td><td>Opt-in tracker submission (numeric metrics only)</td></tr>
        </tbody>
      </table>

      <h2 id="submit">submit and privacy</h2>
      <p>By default nothing leaves your machine. <code>cngx submit</code> is opt-in, shows the exact JSON before sending, and posts only after you confirm.</p>
      <p>Submitted payloads contain only: model name, timestamp, numeric metrics, drift score, and your baseline label. No prompts, outputs, trace IDs, or task names. The submit API does not log your IP or request headers; stored objects contain payload fields only.</p>
      <p>No GitHub account or pull request is required.</p>
      {blocks["submit"]}

      <h2 id="schema">tracker schema</h2>
      <p>Each community record is one JSON object (schema version 1):</p>
      <table class="docs-table">
        <thead><tr><th>Field</th><th>Type</th><th>Description</th></tr></thead>
        <tbody>
          <tr><td><code>schema_version</code></td><td>int</td><td>Always <code>1</code></td></tr>
          <tr><td><code>record_id</code></td><td>string</td><td>UUID</td></tr>
          <tr><td><code>timestamp</code></td><td>string</td><td>ISO-8601 UTC</td></tr>
          <tr><td><code>model</code></td><td>string</td><td>Model name</td></tr>
          <tr><td><code>baseline_label</code></td><td>string</td><td>Submitter's baseline label</td></tr>
          <tr><td><code>drift_score</code></td><td>float</td><td>0 to 1 vs baseline</td></tr>
          <tr><td><code>depth</code></td><td>int</td><td>Reasoning depth</td></tr>
          <tr><td><code>verification_steps</code></td><td>int</td><td>Verification step count</td></tr>
          <tr><td><code>hedging_ratio</code></td><td>float</td><td>Uncertainty language ratio</td></tr>
        </tbody>
      </table>

      <footer class="site-footer">
        <p>Full mkdocs source: <a href="{GITHUB_REPO}/tree/main/docs">github.com/aadi-joshi/cngx/docs</a></p>
      </footer>
    </main>
  </div>
  <script src="../docs.js"></script>
</body>
</html>
"""
    )


def write_data_js(community_by_model: dict, annotations: list[dict]) -> None:
    path = SITE_DIR / "data.js"
    meta = {
        "community_record_count": sum(len(v) for v in community_by_model.values()),
        "community_models": list(community_by_model.keys()),
        "annotations": annotations,
        "live_data_policy": LIVE_DATA_POLICY,
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write("window.TRACKER_DATA = ")
        json.dump(community_by_model, f, indent=2)
        f.write(";\nwindow.TRACKER_META = ")
        json.dump(meta, f, indent=2)
        f.write(";\n")
        if _tracker_live_index_url():
            f.write("window.TRACKER_LIVE_URL = ")
            json.dump(_tracker_live_index_url(), f)
            f.write(";\n")


def copy_static_assets() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    docs_dir = SITE_DIR / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    if not STATIC_DIR.is_dir():
        return
    for name in ("site.css", "app.js", "docs.js"):
        src = STATIC_DIR / name
        if src.exists():
            shutil.copy2(src, SITE_DIR / name)
    for name in ("logo-light.svg", "logo-dark.svg", "logo.png"):
        src = ASSETS_DIR / name
        if src.exists():
            shutil.copy2(src, SITE_DIR / name)
    # docs.js also at site root (already copied); docs page references ../docs.js


def main() -> None:
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    community = load_community_records()
    samples = load_sample_records()
    annotations = load_annotations()

    community_by_model = aggregate_by_model(community)

    copy_static_assets()
    write_data_js(community_by_model, annotations)

    index = SITE_DIR / "index.html"
    with open(index, "w", encoding="utf-8") as f:
        f.write(render_index(len(community)))

    docs_index = SITE_DIR / "docs" / "index.html"
    with open(docs_index, "w", encoding="utf-8") as f:
        f.write(render_docs())

    print(f"Built tracker site: {index}")
    print(f"  Docs: {docs_index}")
    print(
        f"  Embedded community records (fallback): {len(community)} "
        f"({', '.join(community_by_model.keys()) or 'none'})"
    )
    print(f"  Sample records (build tests only): {len(samples)}")
    print(f"  Live data policy: {LIVE_DATA_POLICY}")


if __name__ == "__main__":
    main()
