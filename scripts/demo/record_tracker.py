#!/usr/bin/env python3
"""Record a scripted Playwright demo of the public drift tracker site.

Builds tracker/site/, serves it locally, records WebM with a visible cursor overlay,
then writes docs/assets/tracker-demo.mp4, tracker-demo.gif, and tracker-demo.png.

Requires: pip install -e ".[dev]" && playwright install chromium
"""

from __future__ import annotations

import http.server
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TRACKER_ROOT = REPO_ROOT / "tracker"
SITE_DIR = TRACKER_ROOT / "site"
ASSETS_DIR = REPO_ROOT / "docs" / "assets"

VIEWPORT_W = 1280
VIEWPORT_H = 720

CURSOR_INIT_JS = """
() => {
  if (document.getElementById('demo-cursor')) return;
  const style = document.createElement('style');
  style.textContent = `
    #demo-cursor {
      position: fixed;
      width: 18px;
      height: 18px;
      border: 2px solid #4ade80;
      border-radius: 50%;
      background: rgba(74, 222, 128, 0.25);
      pointer-events: none;
      z-index: 99999;
      left: 0;
      top: 0;
      transform: translate(-50%, -50%);
      transition: left 0.18s ease-out, top 0.18s ease-out;
      box-shadow: 0 0 12px rgba(74, 222, 128, 0.45);
    }
    #demo-cursor::after {
      content: '';
      position: absolute;
      left: 50%;
      top: 50%;
      width: 4px;
      height: 4px;
      background: #4ade80;
      border-radius: 50%;
      transform: translate(-50%, -50%);
    }
  `;
  document.head.appendChild(style);
  const el = document.createElement('div');
  el.id = 'demo-cursor';
  document.body.appendChild(el);
  window.__moveDemoCursor = (x, y) => {
    el.style.left = x + 'px';
    el.style.top = y + 'px';
  };
}
"""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_tracker() -> None:
    subprocess.run([sys.executable, str(TRACKER_ROOT / "build.py")], check=True, cwd=REPO_ROOT)


def _start_static_server(port: int) -> http.server.ThreadingHTTPServer:
    site = str(SITE_DIR)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=site, **kwargs)

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    return httpd


def _smooth_scroll(page, total_px: int, steps: int = 10, delay_ms: int = 350) -> None:
    step = max(1, total_px // steps)
    for _ in range(steps):
        page.evaluate(f"window.scrollBy({{ top: {step}, behavior: 'smooth' }})")
        page.wait_for_timeout(delay_ms)


def _move_cursor(page, x: float, y: float) -> None:
    page.mouse.move(x, y)
    page.evaluate(f"window.__moveDemoCursor({x}, {y})")


def _ease_move(page, x0: float, y0: float, x1: float, y1: float, steps: int = 12) -> None:
    for i in range(1, steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t
        y = y0 + (y1 - y0) * t
        _move_cursor(page, x, y)
        page.wait_for_timeout(40)


def _run_recording(url: str, raw_webm: Path) -> None:
    from playwright.sync_api import sync_playwright

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    video_dir = raw_webm.parent

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": VIEWPORT_W, "height": VIEWPORT_H},
            record_video_dir=str(video_dir),
            record_video_size={"width": VIEWPORT_W, "height": VIEWPORT_H},
            color_scheme="dark",
        )
        page = context.new_page()
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector("#model-tabs .tab", timeout=15000)
        page.evaluate(CURSOR_INIT_JS)
        page.wait_for_timeout(1200)

        _move_cursor(page, VIEWPORT_W * 0.5, VIEWPORT_H * 0.35)
        page.wait_for_timeout(800)

        _smooth_scroll(page, 420, steps=8, delay_ms=320)
        page.wait_for_timeout(600)

        _smooth_scroll(page, 380, steps=7, delay_ms=320)
        page.wait_for_timeout(900)

        tabs = page.locator("#model-tabs .tab")
        count = tabs.count()
        tab_idx = 1 if count > 1 else 0
        tab = tabs.nth(tab_idx)
        box = tab.bounding_box()
        cx, cy = VIEWPORT_W * 0.5, 280.0
        if box:
            cx = box["x"] + box["width"] / 2
            cy = box["y"] + box["height"] / 2
            _ease_move(page, VIEWPORT_W * 0.5, 280, cx, cy)
            page.wait_for_timeout(200)
            tab.hover()
            page.wait_for_timeout(400)
            tab.click()
            page.wait_for_timeout(1200)

        chart = page.locator("#chart-depth")
        chart.wait_for(state="visible", timeout=5000)
        cbox = chart.bounding_box()
        if cbox:
            tx = cbox["x"] + cbox["width"] * 0.72
            ty = cbox["y"] + cbox["height"] * 0.45
            _ease_move(page, cx, cy, tx, ty)
            page.wait_for_timeout(200)
            _move_cursor(page, tx, ty)
            page.mouse.move(tx, ty)
            page.wait_for_timeout(2500)

        page.wait_for_timeout(1000)

        screenshot_path = ASSETS_DIR / "tracker-demo.png"
        page.screenshot(path=str(screenshot_path), full_page=False)

        video = page.video
        context.close()
        browser.close()

        if video is None:
            raise RuntimeError("Playwright did not produce a video")
        recorded = Path(video.path())
        if recorded != raw_webm:
            shutil.move(str(recorded), str(raw_webm))
        print(f"Raw WebM: {raw_webm} ({raw_webm.stat().st_size} bytes)")


def _ffmpeg_trim_and_convert(raw_webm: Path, mp4_out: Path, gif_out: Path, trim_start: float = 0.35) -> None:
  ffmpeg = shutil.which("ffmpeg")
  if not ffmpeg:
      raise RuntimeError("ffmpeg not found on PATH")

  trimmed = raw_webm.with_suffix(".trim.webm")
  subprocess.run(
      [ffmpeg, "-y", "-ss", str(trim_start), "-i", str(raw_webm), "-c", "copy", str(trimmed)],
      check=True,
      capture_output=True,
  )

  subprocess.run(
      [
          ffmpeg,
          "-y",
          "-i",
          str(trimmed),
          "-c:v",
          "libx264",
          "-crf",
          "20",
          "-preset",
          "medium",
          "-movflags",
          "+faststart",
          "-an",
          str(mp4_out),
      ],
      check=True,
      capture_output=True,
  )

  subprocess.run(
      [
          ffmpeg,
          "-y",
          "-i",
          str(mp4_out),
          "-t",
          "10",
          "-vf",
          "fps=8,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse",
          "-loop",
          "0",
          str(gif_out),
      ],
      check=True,
      capture_output=True,
  )
  trimmed.unlink(missing_ok=True)


def _probe(path: Path) -> dict[str, str]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    out = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info: dict[str, str] = {}
    for line in out.stdout.strip().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k] = v
    return info


def main() -> int:
    print("Building tracker site...")
    _build_tracker()
    if not (SITE_DIR / "index.html").is_file():
        raise SystemExit(f"Missing built site: {SITE_DIR / 'index.html'}")

    port = _free_port()
    httpd = _start_static_server(port)
    url = f"http://127.0.0.1:{port}/index.html"

    with tempfile.TemporaryDirectory(prefix="cogscope-tracker-demo-") as tmp:
        raw_webm = Path(tmp) / "tracker-demo.webm"
        try:
            print(f"Recording {url} ...")
            _run_recording(url, raw_webm)
        finally:
            httpd.shutdown()

        mp4_out = ASSETS_DIR / "tracker-demo.mp4"
        gif_out = ASSETS_DIR / "tracker-demo.gif"
        print("Converting with ffmpeg...")
        _ffmpeg_trim_and_convert(raw_webm, mp4_out, gif_out)

    for p in (mp4_out, gif_out, ASSETS_DIR / "tracker-demo.png"):
        if p.is_file():
            info = _probe(p) if p.suffix in {".mp4", ".gif"} else {}
            extra = ""
            if info:
                extra = f" ({info.get('width', '?')}x{info.get('height', '?')}, {float(info.get('duration', 0)):.1f}s)"
            print(f"Wrote {p} ({p.stat().st_size // 1024} KB{extra})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
