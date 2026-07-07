# Demo asset regeneration

Scripts in this folder produce README and docs media. They are **not** runtime dependencies of the `cogscope` package. Install with `pip install -e ".[dev]"`.

## Terminal quickstart (VHS)

We use [VHS](https://github.com/charmbracelet/vhs) (Charmbracelet) for deterministic terminal GIFs. Asciinema does not run on Windows (`fcntl` is Unix-only).

### Prerequisites

Install all three on your PATH:

| Tool | Windows | macOS | Linux |
|------|---------|-------|-------|
| VHS | `winget install charmbracelet.vhs` | `brew install vhs` | see VHS README |
| ttyd | see **Windows note** below | `brew install ttyd` | `apt install ttyd` |
| ffmpeg | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `apt install ffmpeg` |

Verify:

```bash
vhs --version
ttyd --version
ffmpeg -version
```

### Windows 11 25H2 note (ttyd)

The winget `ttyd` package (MinGW build) fails to spawn shells on Windows 11 build 26200+ (`CreateProcessW` error 123). Use the MSVC build instead:

```powershell
scripts/demo/install_ttyd_msvc.ps1
$env:Path = "$PWD\.vhs-tools;$env:Path"
```

Or run the all-in-one recorder (downloads MSVC ttyd automatically):

```powershell
scripts/demo/record_quickstart.ps1
```

References: [ttyd#1501](https://github.com/tsl0922/ttyd/issues/1501), [djdarcy/ttyd-msvc](https://github.com/djdarcy/ttyd-msvc/releases/tag/1.7.7-msvc1).

### Record quickstart GIF

From the repository root:

```bash
pip install -e .
vhs scripts/demo/quickstart.tape
```

Writes `docs/assets/quickstart.gif` (~50 KB, ~13 s at current settings).

**Windows:** `scripts/demo/record_quickstart.ps1`  
**macOS/Linux:** `scripts/demo/record_quickstart.sh`

Inspect file size before committing. Adjust `Set Framerate`, `Sleep`, and `Set PlaybackSpeed` in `scripts/demo/quickstart.tape` if needed.

### Static SVG fallback (optional)

For a single still frame (lightweight docs mirrors, no animation):

```bash
python scripts/record_quickstart_demo.py
```

Writes `docs/assets/quickstart.svg`. The README and docs use the **GIF** as the primary demo asset.

### Watch dashboard

`cogscope watch` was **not** recorded. The live TUI reads events from an in-process bus fed only by the proxy, and the proxy forwards to real provider APIs (no mock upstream). A honest recording would need live API keys and timing-dependent traffic.

## Public drift tracker (Playwright)

Records the locally built tracker site with smooth scroll, model-tab interaction, chart hover, and a visible cursor overlay.

### Prerequisites

```bash
pip install -e ".[dev]"
playwright install chromium
```

`ffmpeg` must be on your PATH for WebM to MP4/GIF conversion.

### Record

```bash
python scripts/demo/record_tracker.py
```

**Outputs:**

| File | Use |
|------|-----|
| `docs/assets/tracker-demo.gif` | Primary README/docs embed (~1.7 MB, autoplays on GitHub) |
| `docs/assets/tracker-demo.mp4` | Full-quality linked asset (~2.2 MB, 1280x720) |
| `docs/assets/tracker-demo.png` | Static fallback screenshot |

The script builds `tracker/site/` first, serves it on a random localhost port, records with Playwright `recordVideo`, trims leading blank frames, then converts with ffmpeg.

Static-only screenshots (no video): `python tracker/scripts/capture_screenshots.py`
