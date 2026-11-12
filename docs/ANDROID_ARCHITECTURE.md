# SnapMitra Mobile – Android architecture assessment

**Status: assessment only. No Android app has been built or tested.** Everything below marked *measured* was measured on a
desktop-class CPU (single core, Linux) as a proxy; nothing has been run on a phone yet. Android items 18–24 of your test list
are therefore all **NOT TESTED**.

## 1. Recommendation (short)

| Decision | Recommendation |
|---|---|
| App technology | **Native Android – Kotlin + Jetpack Compose**, using the official **ONNX Runtime for Android** (`onnxruntime-android`) |
| Offline / privacy | Models **bundled inside the APK**; all processing on the phone; no server, no account, no upload |
| Sharing logic with Windows | Share **the specification, the models and golden test vectors** (`docs/parity_vectors.json`), not code. The Python app stays the reference implementation |
| Background model on the phone | **u2net int8 (44 MB)** as default, **u2netp (4.6 MB)** as fallback for low-RAM phones – decide after an on-device test |
| Not recommended as the main path | PWA, cloud/LAN backend. Flutter is a reasonable second choice (see §4) |
| Fallback if the Kotlin port is too costly | Embed the existing Python code with Chaquopy (needs a 1–2 day spike first – see §4, option E) |

## 2. What the current Windows code looks like (inspection)

The Windows app is already split into small modules, which is what makes a port practical:

| Concern | Windows module | Depends on | Portable how |
|---|---|---|---|
| 1 Image processing (load, EXIF, downscale to 1600 px, affine crop/rotate, brightness/contrast/sharpness) | `imaging.py` | Pillow, NumPy | re-implement with Android `Bitmap`/`Canvas`/`Matrix` (spec + vectors) |
| 2 Background removal | `model.py` (`MaskModel`) | ONNX Runtime, NumPy | **same `.onnx` file** via ORT Android; ~25 lines of pre/post-processing |
| 3 Face detection | `model.py` (`FaceModel`) | ONNX Runtime | **same `.onnx` file**; box-merge logic ~25 lines |
| 4 Cropping / head geometry | `imaging.py` (`analyse`, `default_crop`, `effective_head`) | NumPy | pure arithmetic → straightforward; **golden vectors provided** |
| 5 Text rendering | `textoverlay.py` | Pillow fonts | Android `Canvas` + `Paint`/`StaticLayout`; text *rules* (resolve, fit, 3 positions) portable; **vectors provided** |
| 6 Sheet generation | `layout.py` | Pillow | grid/packing is pure arithmetic → easy + **vectors provided**; page drawing via `Canvas` |
| 7 Export | `layout.save_pages` | Pillow | PNG/JPG via `Bitmap.compress`, PDF via `android.graphics.pdf.PdfDocument` |
| UI / orchestration | `app.py`, `ui_*.py`, `worker.py` | Tkinter | re-write in Compose (ViewModel + coroutines replace the worker thread/queue) |

Pure-logic pieces (units, grid, continuous packing, orientation choice, text resolution, caption/fixed-canvas heights,
head-size maths, crop geometry) are exactly the parts with the most business rules – and they are tiny and deterministic.
`tools/make_parity_vectors.py` writes **`docs/parity_vectors.json`** (128 grid cases, 9 packing cases, text, crop and
fixed-canvas cases) from the Python code; `tests/run_tests.py` fails if the file goes stale. An Android port can run these as
plain JVM unit tests in CI without a phone.

## 3. Can the ONNX models run on a phone? (measured on desktop as a proxy)

Both models use only standard operators (U²-Net: opset 11, 13 op types – Conv, Relu, MaxPool, Resize, Sigmoid, Concat, Add,
Slice, …; face detector: 17 standard ops), which the official ONNX Runtime Android package supports.
The background model needs a **fixed 320×320 input** (a 256×256 test failed).

| Model | File | RAM after load | Peak RAM (default) | Peak RAM (arena off*) | Inference, 1 thread | Mask IoU vs fp32 (2 photos) |
|---|---|---|---|---|---|---|
| u2net fp32 (**current**) | 176 MB | 418 MB | 891 MB | 518 MB | ≈1.2 s | 1.000 |
| u2net int8 (dynamic quantisation) | 44 MB | 62 MB | 556 MB | 393 MB | ≈0.9 s | 0.992 |
| u2netp fp32 (small) | 4.6 MB | 22 MB | 494 MB | 302 MB (224 MB with basic graph optimisation, ≈0.7 s) | ≈0.45 s | 0.994 |
| Face detector (RFB-320) | 1.3 MB | 11 MB | 28 MB | – | ≈13 ms | – |

\* `enable_cpu_mem_arena = false`, `enable_mem_pattern = false`. The `.ort` mobile format was also produced from u2netp (4.8 MB) and loads/runs.
Reproduce: `python tools/benchmark_models.py <models_dir> <photo> [<photo>...]` (results in `docs/android_feasibility_results.json`).

What this means:

* **Peak RAM is dominated by activations, not weights** (even the 4.6 MB model peaks near 500 MB by default). On a 2–3 GB phone that is risky; with the arena disabled the u2net int8 / u2netp peaks (≈300–400 MB, native memory) are realistic. The full 176 MB fp32 model (≈520–890 MB peak) is **not** advisable on low-end phones.
* Quality: on a plain-background portrait the int8 cut-out is visually closest to the full model; u2netp shows a slight soft halo on hair edges. **Only 2 photos were compared – validate on ≥20 real customer-style photos before choosing.**
* Unknown until tested on a real phone: actual speed (phone CPUs vary; int8 speed depends on the ARM instruction set), thermal throttling, and low-memory kills. Run the model on the father's actual phone in Milestone A0.
* Large camera photos are handled like on Windows: decode with `inSampleSize` to ≤1600 px (the Python app does the same), so a 12–50 MP photo never becomes a full-size bitmap.

## 4. Options compared

| Criterion | **A. Native Kotlin + Compose** | B. Flutter | C. PWA | D. Shared backend | E. Kotlin UI + embedded Python (Chaquopy) |
|---|---|---|---|---|---|
| Works offline / no upload | ✅ | ✅ | △ (model must be cached in the browser; storage can be evicted) | ❌ cloud / △ LAN-only | ✅ |
| ONNX Runtime support | ✅ official AAR, best supported | △ community plugins or own platform channel | △ ORT-Web (WASM): slower, mobile-browser memory limits | n/a (server) | △ needs an `onnxruntime` wheel for Android – **not verified**; or call the Java AAR |
| Speed / memory control | ✅ native, full control of session options | △ extra layers | ❌ weakest | ✅ server | △ interpreter + NumPy/Pillow overhead, bigger APK (~+60–100 MB, estimate) |
| Gallery pick (multi) / save to gallery / PDF / native share sheet (WhatsApp, Gmail, Bluetooth) | ✅ all first-class platform APIs | ✅ via plugins | △ Web Share API (files) works in Chrome; save-to-gallery is awkward | n/a | ✅ (Kotlin side) |
| Re-use of the working Python code | ❌ re-implement (spec + vectors) | ❌ re-implement in Dart | ❌ re-implement in JS | ✅ | ✅ **highest reuse (imaging/layout/text unchanged)** |
| Result identical to Windows | verified by vectors | verified by vectors | verified by vectors | identical | **identical by construction** |
| Verifiable in GitHub CI without a device | ✅ JVM unit tests (vectors) + emulator tests | ✅ | △ | ✅ | △ |
| Maintenance for one maintainer | ✅ one platform, fewest moving parts | △ Flutter + plugin churn | △ | ❌ needs a server | △ two languages + packaging risk |
| iPhone later | ❌ | ✅ | ✅ | ✅ | ❌ |
| Fits "no mandatory cloud, offline-first" | ✅ | ✅ | △ | ❌ | ✅ |

Notes:
* **D (backend):** a cloud service breaks the privacy promise and the "no mandatory cloud" rule → rejected. A *LAN mode* where the phone talks to SnapMitra on the shop PC would avoid the cloud but needs the PC on and on the same Wi-Fi; it is not an independent phone app. Possible later add-on, not the foundation.
* **C (PWA):** attractive (no install, could even replace the desktop UI) but the weakest fit for a 44–176 MB model, memory limits and cache eviction; it would also mean rewriting everything in JavaScript.
* **B (Flutter):** good UI tooling and a future iOS path, but ONNX Runtime and PDF/image processing would go through plugins or Dart FFI – more places for blind-development surprises. Choose it only if iPhone support becomes a requirement.
* **E (Chaquopy):** the fastest way to get *identical* output because `imaging.py`, `layout.py` and `textoverlay.py` run unchanged. Risks I could not verify: availability of `onnxruntime`/Pillow/NumPy builds for the chosen Python/Android ABI, APK size and start-up time. It deserves a **1–2 day spike** (an APK that imports them and runs the model on a real phone). If the spike is clean and the Kotlin port looks expensive, E becomes the pragmatic choice.

**Why A:** the work is mostly (a) a small, well-specified logic port that can be machine-checked against vectors, and (b) Android integration (picker, MediaStore, PdfDocument, share sheet) where native APIs are the most reliable. No interpreter, smallest memory use, best fit for a low-end phone.

## 5. How each requested feature maps to Android

| Requirement | Android mechanism |
|---|---|
| Select photos from gallery, multiple | Photo Picker `ActivityResultContracts.PickMultipleVisualMedia` (no storage permission needed on Android 13+; falls back automatically on older versions) |
| Background removal / face detection offline | ORT Android + bundled models (§3); run on a background coroutine dispatcher; progress + cancel like the Windows worker |
| Presets, custom size (mm / in), copies per photo, global + individual text, background & text colours | Same data model and rules as Windows (`parity_vectors.json`) |
| Photo preview / sheet preview | Compose `Image` of a down-scaled bitmap |
| PNG / JPG export (300 DPI) | `Bitmap.compress` (+ write DPI in metadata via `ExifInterface` for JPEG) |
| PDF export (exact paper size) | `android.graphics.pdf.PdfDocument`, page size in 1/72 inch (A4 = 595×842 pt), draw each page bitmap |
| Save to phone gallery | `MediaStore` (Pictures/SnapMitra), scoped storage – no broad permission |
| Share via WhatsApp / Gmail / Bluetooth / others | **Native share sheet:** `FileProvider` URI + `Intent.ACTION_SEND` / `ACTION_SEND_MULTIPLE` + `createChooser` with MIME `image/png`, `image/jpeg` or `application/pdf`. WhatsApp, Gmail and Bluetooth appear because they are installed share targets – **no private WhatsApp API, no automation** |
| Large images | `inSampleSize` / `ImageDecoder.setTargetSize`, EXIF rotation, cap at 1600 px (as on Windows); write PDF page by page to keep memory low |

Practical note on WhatsApp: it recompresses photos. For printing, **share the PDF (sent as a document) or PNG as a document** to keep full quality.

## 6. Suggested milestones (each with an acceptance test)

| # | Milestone | Acceptance |
|---|---|---|
| A0 | **Feasibility spike on the real phone** (and a Chaquopy spike if desired): ORT + u2netp/int8 + face model on a test image; log time, RAM, quality; compare ≥20 photos | numbers in this document replaced by phone measurements; model choice made |
| A1 | Kotlin core module (no UI): units, presets, grid, continuous packing, orientation, text rules, crop geometry, fixed canvas | **all vectors in `docs/parity_vectors.json` pass as JVM unit tests in GitHub Actions** |
| A2 | Image pipeline on `Bitmap`: load/EXIF/downscale, crop/rotate/adjust, background colours, text render (3 positions), cell sizes exact in px | instrumented tests (emulator): cell sizes equal vectors; fixed canvas exact; same-photo duplicates identical |
| A3 | Sheet + export: pages, guides, border, PNG/JPG/PDF | PDF MediaBox and pixel size checks, as in `tests/run_tests.py` |
| A4 | UI: picker, list with copies, Edit text, editing, layout, preview | manual test on phone |
| A5 | Gallery save + share sheet | manual test: share PDF/PNG/JPG to WhatsApp, Gmail, Bluetooth |
| A6 | Signed APK built by GitHub Actions; offline test in flight mode | install on father's phone, full job with Wi-Fi/data off |

## 7. Questions I need you to decide

1. Lowest phone you must support (Android version, RAM)? This decides int8 vs u2netp.
2. Distribute as an APK file you install directly (simplest) or via Google Play?
3. Is an iPhone version ever needed (would favour Flutter)?
4. OK to bundle the 44 MB int8 model (APK ≈ 60–70 MB)?

## 8. Test status for the Android items (from your list)

| # | Item | Status |
|---|---|---|
| 18 | Gallery image selection | **Not tested** – no Android app yet |
| 19 | Multiple image selection | **Not tested** |
| 20 | Background removal | Model feasibility **measured on desktop only** (§3); on-device **not tested** |
| 21 | Offline processing | Windows app tested offline; Android **not tested** |
| 22 | PNG/JPG/PDF generation | Reference behaviour tested on Windows; Android **not tested** |
| 23 | WhatsApp sharing | **Not tested** (design in §5) |
| 24 | Large image handling | Windows tested (6000×4000 → 1600 px); Android **not tested** |
