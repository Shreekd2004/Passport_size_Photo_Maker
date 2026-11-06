<p align="center"><img src="assets/snapmitra_logo.png" width="220" alt="SnapMitra"></p>

# SnapMitra – Your Smart Photo & Print Studio

Fast passport, stamp-size, visa and ID photo sheets for a photography / stationery / Xerox shop.
**100 % offline** – customer photos are processed on the PC and never uploaded. No account, no Python, no admin rights needed.

## What it does
| Section | Features |
|---|---|
| **1 Photos** | Add photos · import folder · drag & drop · thumbnails · per-photo copies · reorder · duplicate · remove · clear all |
| **2 Editing** | AI background removal (or keep original) · White / Light blue / Blue / Red / custom colour · zoom · move · rotate · brightness · contrast · sharpness · **text overlay** (customer name, date, custom text; font, size, colour, bold, alignment; *inside* or *below* the photo; optional background; live preview) |
| **3 Layout** | Photo sizes (Indian Passport 35×45, Stamp 25×25, US Passport 2×2 in, visa presets, **custom in mm or inches**, save your own) · A4 / A5 / 4×6 in / 5×7 in / custom paper · orientation (auto picks the best) · margins · gaps · border · **cutting guides** (thin / dotted) · **layout mode: Continuous packing (default) or Group by photo** |
| **4 Preview & Export** | Sheet preview with page navigation · PNG / JPG / **PDF** (exact paper size) · output folder · print to any installed Windows printer at actual size |
| Extras | Dashboard · recent projects · save/open project · auto-save & "Continue last session" · undo / redo · keyboard shortcuts (F1) · tooltips |

### Continuous packing
All photos are one sequence in upload order. Example – P1×4, P2×1, P3×8, P4×3 on 5 columns:
```
P1 P1 P1 P1 P2
P3 P3 P3 P3 P3
P3 P3 P3 P4 P4
P4
```
Grid size is calculated from the real printable area (paper − margins, photo size, gaps, text strip, border, guides) – never a fixed "5 per row".

## Get the Windows app (no development tools needed)
1. Put these files in your GitHub repository (see *Replacing the files* below).
2. **Actions → Build SnapMitra for Windows → Run workflow** (≈ 10–15 min). The build runs the app's own self-test and fails loudly if anything is broken.
3. Download the artifact **SnapMitra-Windows**: `SnapMitra-Setup.exe` (installer, no admin rights, desktop shortcut) and `SnapMitra-portable.zip`.
4. Copy the installer to the shop PC (pen drive) and run it. SmartScreen: *More info → Run anyway* (the app is not code-signed).

### Replacing the files in your GitHub repo
Open the repo → **Add file → Upload files** → drag in the **contents** of the zip (all files *and* the `assets`, `tools`, `tests`, `.github` folders; not the zip itself) → **Commit**. Files with the same name are replaced. Then open `tests/test_core.py` (old, no longer used) and delete it.

## Project structure
```
main.py            entry point, splash, --selftest
app.py             main window, jobs, undo/redo, projects, shortcuts
ui_photos.py  ui_editing.py  ui_layout.py  ui_preview.py  ui_home.py   the four sections + dashboard/about/splash
imaging.py         photo pipeline (mask, face, crop, adjustments)      textoverlay.py   text overlay
layout.py          continuous packing, guides, pages, export           worker.py        background thread
model.py           ONNX models (bundled / cached / one-time download)  printing.py      Windows printing
presets.py  settings.py  units.py  branding.py  ui_widgets.py
assets/            logo, icons (.ico), splash, installer images, fonts
SnapMitra.spec     PyInstaller config            installer.iss   Inno Setup installer
tools/             fetch_model.py  make_assets.py  make_sample.py
tests/             run_tests.py  gui_tests.py  sample_portrait.png  last_results.txt
.github/workflows/build.yml
```

## Build locally (optional)
```
pip install -r requirements.txt
python tools/fetch_model.py          # downloads the two AI models into ./models
pyinstaller --noconfirm SnapMitra.spec
```
Run the tests: `python tests/run_tests.py` (and `python tests/gui_tests.py` with a display).

## Notes
* **Models:** U2-Net (background, Apache-2.0) and Ultra-Light-Fast-Generic-Face-Detector (face, MIT) run through ONNX Runtime. They are bundled in the installer; if ever missing, a one-time download with progress and Retry is offered.
* **rembg was removed on purpose:** it pulled in numba/scipy and took ~50 s to start on first launch. The same U2-Net model is now called directly (identical masks, 5 s total cold start). OpenCV is not used.
* **Data:** `%LOCALAPPDATA%\SnapMitra` (settings, projects auto-save, `presets.json`, `log.txt`).
* **Add sizes:** *Save as preset…* in Layout, or edit `presets.json`.
* Visa presets list the country and requirements – rules change, always verify with the issuing authority.
