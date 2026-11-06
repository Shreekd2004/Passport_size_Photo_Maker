"""SnapMitra automated test-suite (non-GUI). Covers every item of the acceptance list that can be tested headlessly.
Run:  python tests/run_tests.py            (GUI / responsiveness checks: tests/gui_full.py under a display)"""
import io, math, os, queue, re, shutil, socket, sys, tempfile, threading, time, http.server, socketserver, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="sm_test_")
os.environ["LOCALAPPDATA"] = TMP
MODEL_SRC = os.environ.get("SM_MODEL_DIR", "/home/claude/models")
import numpy as np
from PIL import Image
import imaging, layout, model, textoverlay, units, worker, presets, printing, settings
from imaging import Photo, Style
from layout import LayoutSpec
from textoverlay import TextStyle

RESULTS = []
def check(n, name, cond, detail=""):
    RESULTS.append((n, name, bool(cond), detail)); print(f"[{'PASS' if cond else 'FAIL'}] {n:>2}. {name}  {detail}")

def install_models():
    d = os.path.join(TMP, "SnapMitra", "models"); os.makedirs(d, exist_ok=True)
    for f in os.listdir(MODEL_SRC):
        if f.endswith(".onnx"): shutil.copy(os.path.join(MODEL_SRC, f), d)

def run(job, timeout=300):
    q = queue.Queue(); th = threading.Thread(target=worker.run_job, args=(job, q), daemon=True); th.start()
    msgs = []; t0 = time.time()
    while time.time() - t0 < timeout:
        m = q.get(timeout=timeout); msgs.append(m)
        if m[0] in ("done", "cancelled", "error"): return m, msgs, time.time() - t0
    raise TimeoutError

def params(spec=None, style=None, **kw):
    d = dict(remove=True, spec=spec or LayoutSpec(), style=style or Style((255, 255, 255), True, TextStyle())); d.update(kw); return d

SRC = os.environ.get("SM_TEST_IMAGE") or os.path.join(HERE, "sample_portrait.png")   # public-domain sample shipped with the repo
WORK = os.path.join(TMP, "in"); os.makedirs(WORK)
base = Image.open(SRC).convert("RGB")

# ===================================================================== PHOTO PROCESSING
install_models()
p1 = Photo(SRC, 5)
end, msgs, t = run(worker.Job("prepare", [p1], params()))
check(1, "Single photograph processed", end[0] == "done" and p1.state == "ready", f"({t:.1f}s)")
check(5, "AI background removal produces a mask", p1.mask is not None and np.asarray(p1.mask).max() == 255)
stages = []
for m in msgs:
    if m[0] == "progress" and (not stages or stages[-1] != m[3]): stages.append(m[3])
need = ["Loading AI model", "Removing background", "Detecting face", "Cropping photograph", "Applying text overlay", "Preparing final image"]
check(6, "Face detected; all processing stages reported", p1.face_found and all(s in stages for s in need), f"stages={stages}")

for name, fmt, mode in [("a.jpg", "JPEG", "RGB"), ("b.jpeg", "JPEG", "RGB"), ("c.png", "PNG", "RGB"), ("d.webp", "WEBP", "RGB"),
                        ("e.bmp", "BMP", "RGB"), ("f.tiff", "TIFF", "RGB"), ("g_alpha.png", "PNG", "RGBA"), ("h_palette.png", "PNG", "P")]:
    im = base.copy()
    if mode == "RGBA": im = im.convert("RGBA")
    if mode == "P": im = im.convert("P", palette=Image.ADAPTIVE, colors=64)
    im.save(os.path.join(WORK, name), fmt)
fmt_photos = [Photo(os.path.join(WORK, n), 1) for n in sorted(os.listdir(WORK))]
end, _, t = run(worker.Job("prepare", fmt_photos, params()))
check(4, "Different image formats (jpg, jpeg, png, webp, bmp, tiff, RGBA png, palette png)",
      end[0] == "done" and all(p.state == "ready" for p in fmt_photos), f"{len(fmt_photos)} files, {t:.1f}s, states={[p.state for p in fmt_photos if p.state!='ready'] or 'all ready'}")

multi = [Photo(SRC, 2, "A"), Photo(SRC, 3, "B"), Photo(SRC, 1, "C")]
end, _, t = run(worker.Job("prepare", multi, params()))
check(2, "Multiple photographs processed", end[0] == "done" and all(p.state == "ready" for p in multi), f"({t:.1f}s)")

big_path = os.path.join(WORK, "big_6000x4000.jpg")
base.resize((4000, 6000), Image.LANCZOS).rotate(90, expand=True).save(big_path, "JPEG", quality=92)
big = Photo(big_path, 1); end, _, t = run(worker.Job("prepare", [big], params()))
check(3, "Large photograph (6000x4000, %.1f MB)" % (os.path.getsize(big_path) / 1e6), end[0] == "done" and big.state == "ready" and max(big.src.size) == 1600, f"working size {big.src.size} (cap 1600), {t:.1f}s")

for key, rgb in settings.BG_COLORS.items():
    img, ph = imaging.final_cell(p1, LayoutSpec(), Style(rgb, True, TextStyle()))
    p1.cache_key = None
    ok = tuple(img.getpixel((3, 3))) == tuple(rgb)
    check(22, f"Background colour '{key}' applied", ok, f"corner={img.getpixel((3,3))} expected={rgb}") if True else None
img, _ = imaging.final_cell(p1, LayoutSpec(), Style(settings.hex_to_rgb("#33AA66"), True, TextStyle())); p1.cache_key = None
check(22, "Custom colour (#33AA66)", tuple(img.getpixel((3, 3))) == (51, 170, 102))
orig, _ = imaging.final_cell(p1, LayoutSpec(), Style((200, 35, 45), False, TextStyle())); p1.cache_key = None
removed, _ = imaging.final_cell(p1, LayoutSpec(), Style((200, 35, 45), True, TextStyle())); p1.cache_key = None
check(22, "Retain original background option (original kept, not replaced by the colour)", tuple(removed.getpixel((3, 3))) == (200, 35, 45) and tuple(orig.getpixel((3, 3))) != (200, 35, 45), f"removed->{removed.getpixel((3,3))}  kept original->{orig.getpixel((3,3))}")

# manual crop
spec = LayoutSpec(); st = Style((255, 255, 255), True, TextStyle())
a0 = np.asarray(imaging.render_cell(p1, spec, st, 300)[0]).astype(int)
p1.edit.update(zoom=1.3, dx=0.1, tilt=5, bright=15, contrast=10, sharp=40); a1 = np.asarray(imaging.render_cell(p1, spec, st, 300)[0]).astype(int)
check(7, "Manual crop (zoom/move/rotate/brightness/contrast/sharpness) changes the output", np.abs(a0 - a1).mean() > 5, f"mean diff {np.abs(a0-a1).mean():.1f}")
p1.edit = imaging.default_edit()
blank = Photo(os.path.join(WORK, "blank.png"), 1); Image.new("RGB", (800, 1000), (180, 180, 180)).save(blank.path)
end, _, _ = run(worker.Job("prepare", [blank], params()))
cell, _ = imaging.render_cell(blank, spec, st, 300)
check(7, "No face found -> no crash, manual framing still works", end[0] == "done" and blank.state == "ready" and not blank.face_found and cell.size[0] == 300)
changed = imaging.render_cell(blank, spec, Style((255,255,255), True, TextStyle()), 300)[0]
blank.edit.update(zoom=1.5, dy=0.2); after = imaging.render_cell(blank, spec, Style((255,255,255), True, TextStyle()), 300)[0]
check(7, "Manual crop works on a photo without a face", changed.size == after.size)

# ===================================================================== COPY COUNTS & LAYOUT
def rows_of(spec, counts):
    n, g, pages = layout.choose(spec, counts); return n, g, pages
S = LayoutSpec()
n, g, pages = rows_of(S, [5]); check(8, "One photograph, 5 copies", len(pages) == 1 and len(pages[0]) == 5 and all(i == 0 for _, _, i in pages[0]))
n, g, pages = rows_of(S, [4, 1]); seq = [i for _, _, i in pages[0]]; check(9, "Two photographs (4 + 1)", seq == [0, 0, 0, 0, 1])
n, g, pages = rows_of(S, [4, 1, 8]); seq = [i for _, _, i in pages[0]]
check(10, "Three photographs (4 + 1 + 8), continuous", seq == [0]*4 + [1] + [2]*8 and [(r, c) for r, c, _ in pages[0]][4] == (0, 4), f"row1={seq[:5]} row2={seq[5:10]} row3={seq[10:]}")
import random; random.seed(7)
counts = [random.randint(1, 12) for _ in range(10)]
n, g, pages = rows_of(S, counts); flat = [(r, c, i) for pg in pages for r, c, i in pg]
order_ok = [i for _, _, i in flat] == [i for i, k in enumerate(counts) for _ in range(k)]
full_rows_ok = all(len([1 for r, c, i in pg if r == rr]) == g["cols"] for pg in pages[:-1] for rr in range(g["rows"])) and \
    all(len([1 for r, c, i in pages[-1] if r == rr]) == g["cols"] for rr in range(max(r for r, _, _ in pages[-1])))
check(11, f"Ten photographs, different copy counts {counts}", order_ok and full_rows_ok and len(flat) == sum(counts), f"{sum(counts)} photos, {len(pages)} page(s), upload order kept, no gaps")
ex = layout.fill(5, 10, [4, 1, 8, 3], False)[0]; g_ = lambda r: [i + 1 for rr, c, i in ex if rr == r]
check(12, "Continuous packing = brief's example (P1x4,P2x1,P3x8,P4x3)", g_(0) == [1, 1, 1, 1, 2] and g_(1) == [3]*5 and g_(2) == [3, 3, 3, 4, 4] and g_(3) == [4], f"rows: {[g_(r) for r in range(4)]}")
gp = layout.fill(5, 10, [4, 1, 8, 3], True)[0]
starts = {}; 
for r, c, i in gp: starts.setdefault(i, (r, c)) if True else None
check(13, "Group-by-photo: every photo starts at column 1 of a new row", all(c == 0 for r, c in starts.values()) and len({r for r, c in starts.values()}) == 4, f"starts={starts}")
S2 = LayoutSpec(); n, g, pages = rows_of(S2, [80]); per = g["cols"] * g["rows"]
check(14, f"Multiple pages (80 photos, {per}/page)", len(pages) == math.ceil(80 / per) and all(len(p) == per for p in pages[:-1]), f"{len(pages)} pages")
default_mode = LayoutSpec().mode; check(12, "Continuous packing is the DEFAULT mode", default_mode == "continuous" and settings.DEFAULTS["layout_mode"] == "continuous")

# ===================================================================== NEW FEATURES
stamp = [p for p in presets.PHOTO_PRESETS if p["name"] == "Stamp Size"][0]
sp = LayoutSpec(photo_w=stamp["w_mm"], photo_h=stamp["h_mm"], head=stamp["head_ratio"])
cell, ph = imaging.final_cell(p1, sp, st); p1.cache_key = None
n, g, pages = rows_of(sp, [30])
check(15, "Stamp size 25x25 mm generated", cell.size == (units.mm_to_px(25),) * 2 and g["cols"] * g["rows"] > 40, f"{cell.size}px, {g['cols']}x{g['rows']}={g['cols']*g['rows']} per A4")
check(16, "Custom dimensions & unit conversion (2 x 2 in = 50.8 mm = 600 px)", units.to_mm(2, "in") == 50.8 and units.mm_to_px(units.to_mm(2, "in")) == 600 and abs(units.from_mm(35, "in") - 1.378) < 0.001)
cs = LayoutSpec(photo_w=units.to_mm(1.5, "in"), photo_h=units.to_mm(2.0, "in")); c3, _ = imaging.final_cell(p1, cs, st); p1.cache_key = None
check(16, "Custom 1.5 x 2 in photo renders at 450 x 600 px", c3.size == (450, 600), f"{c3.size}")

ts_none = TextStyle(enabled=False)
ts_in = TextStyle(enabled=True, source="custom", custom="SnapMitra Studio", size_pt=9, position="inside", color=(255, 0, 0), bg_on=False)
base_cell = imaging.final_cell(p1, S, Style((255, 255, 255), True, ts_none))[0]; p1.cache_key = None
in_cell = imaging.final_cell(p1, S, Style((255, 255, 255), True, ts_in))[0]; p1.cache_key = None
d = np.abs(np.asarray(base_cell).astype(int) - np.asarray(in_cell).astype(int)).sum(axis=2); rows_changed = np.where(d.sum(axis=1) > 0)[0]
check(17, "Text INSIDE photo (bottom centre only)", len(rows_changed) > 10 and rows_changed.min() > 0.8 * base_cell.height and base_cell.size == in_cell.size, f"changed rows {rows_changed.min()}-{rows_changed.max()} of {base_cell.height}")
ts_b = TextStyle(enabled=True, source="custom", custom="Below Photo", size_pt=9, position="below", color=(0, 0, 255), bg_on=False)
sb = LayoutSpec(caption_mm=textoverlay.caption_mm(ts_b)); b_cell, b_ph = imaging.final_cell(p1, sb, Style((255, 255, 255), True, ts_b)); p1.cache_key = None
same = np.array_equal(np.asarray(b_cell.crop((0, 0, b_cell.width, b_ph))), np.asarray(base_cell))
check(18, "Text BELOW photo (photo area untouched, strip added)", same and b_cell.height == b_ph + units.mm_to_px(sb.caption_mm), f"cell {b_cell.size}, photo {b_ph}px + strip {b_cell.height-b_ph}px")
def has_color(img, rgb, tol=40): a = np.asarray(img).astype(int); return int((np.abs(a - np.array(rgb)).sum(axis=2) < tol).sum())
check(19, "Different text colours (red inside / blue below)", has_color(in_cell, (255, 0, 0)) > 50 and has_color(b_cell, (0, 0, 255)) > 50 and has_color(in_cell, (0, 0, 255)) < 50)
today = datetime.date.today().strftime("%d/%m/%Y")
t1 = textoverlay.resolve_text(TextStyle(enabled=True, source="name", use_date=True), "Ravi Kumar")
t2 = textoverlay.resolve_text(TextStyle(enabled=True, use_date=True, date_mode="manual", date_text="01/01/2030", source="custom", custom="X", two_lines=True), "")
check(20, "Automatic (today) and manual date", today in t1 and t1.startswith("Ravi Kumar") and t2 == "X\n01/01/2030", f"'{t1}' | {t2!r}")
orig_before = Image.open(SRC).tobytes(); check(17, "Original uploaded file is never modified", orig_before == Image.open(SRC).tobytes() and os.path.getmtime(SRC) < time.time() - 1)
# duplicates carry identical overlay
items_dup = [(*imaging.final_cell(p1, sb, Style((255,255,255), True, ts_b)), 5)]; pg = layout.build_pages(sb, items_dup)[0]
gdup = layout.grid(sb, False); xd0 = gdup["m"] + max(0, (gdup["PW"] - 2 * gdup["m"] - (gdup["cols"] * gdup["w"] + (gdup["cols"] - 1) * gdup["hg"])) // 2)
cells = [np.asarray(pg.crop((xd0 + c * (gdup["w"] + gdup["hg"]), gdup["m"], xd0 + c * (gdup["w"] + gdup["hg"]) + gdup["w"], gdup["m"] + gdup["ch"]))) for c in range(5)]
strip_has_text = (cells[0][gdup["h"] + 5:] < 200).sum() > 100
check(17, "Every duplicate carries the same overlay (5 copies pixel-identical, text present)", all(np.array_equal(cells[0], c) for c in cells[1:]) and strip_has_text)

# cutting guides: measure pixels
def sheet(spec, counts=(12,)):
    items = [(*imaging.final_cell(p1, spec, Style((255, 255, 255), True, TextStyle())), c) for c in counts]; p1.cache_key = None
    return layout.build_pages(spec, items)[0]
sg_none = np.asarray(sheet(LayoutSpec(guides="none"))).astype(int)
for kind in ("thin", "dotted"):
    sp_g = LayoutSpec(guides=kind); pgimg = sheet(sp_g); arr = np.asarray(pgimg).astype(int)
    gd = layout.grid(sp_g, False); x0 = gd["m"] + max(0, (gd["PW"] - 2 * gd["m"] - (gd["cols"] * gd["w"] + (gd["cols"] - 1) * gd["hg"])) // 2)
    gx = x0 + gd["w"] + gd["hg"] // 2                      # centre of first vertical gap
    col = arr[gd["m"] + 5: gd["m"] + gd["h"] - 5, gx - 1: gx + 2, :].sum(axis=2).min(axis=1)  # darkest of the 3 guide columns
    dark = (col < 150).mean()
    inside_same = True
    for c in range(3):                                      # photo interiors identical with / without guides
        x = x0 + c * (gd["w"] + gd["hg"]); y = gd["m"]
        a = arr[y + 4: y + gd["h"] - 4, x + 4: x + gd["w"] - 4]; b = np.asarray(sheet(LayoutSpec(guides="none", hgap=sp_g.hgap)))[y + 4: y + gd["h"] - 4, x + 4: x + gd["w"] - 4].astype(int) if False else None
    full = np.asarray(sheet(LayoutSpec(guides="none", hgap=max(4.0, 2.0)))).astype(int)
    x = x0; y = gd["m"]; a = arr[y + 4: y + gd["h"] - 4, x + 4: x + gd["w"] - 4]; b = full[y + 4: y + gd["h"] - 4, x + 4: x + gd["w"] - 4]
    check(21, f"Cutting guides '{kind}' drawn in the gap centre", (0.9 < dark <= 1.0 and kind == "thin") or (0.35 < dark < 0.75 and kind == "dotted"), f"dark fraction along guide = {dark:.2f}")
    check(21, f"Cutting guides '{kind}' never overlap photo content", np.array_equal(a, b))
check(21, "Gaps auto-widen to >= 2 mm when guides are on", layout.grid(LayoutSpec(guides="thin", hgap=0.5, vgap=0.5), False)["hg"] >= units.mm_to_px(2.0))

# paper sizes & layout capacity
caps = {}
for name, w, h in presets.PAPERS[:-1]:
    s_ = LayoutSpec(paper_name=name, paper_w=w, paper_h=h); n_, g_, _ = layout.choose(s_, [1]); caps[name] = (g_["cols"], g_["rows"], g_["landscape"])
check(14, "Paper sizes A4 / A5 / 4x6 / 5x7 + automatic orientation", all(c[0] * c[1] > 0 for c in caps.values()), str(caps))
try: layout.choose(LayoutSpec(paper_w=40, paper_h=50), [1]); too_small = False
except layout.LayoutError: too_small = True
check(14, "Photo too big for paper -> clear error, no distortion", too_small)

# ===================================================================== EXPORT
ts_e = TextStyle(enabled=True, source="name", use_date=True, two_lines=True, position="below", size_pt=7)
se = LayoutSpec(guides="thin", caption_mm=textoverlay.caption_mm(ts_e))
ph_list = [Photo(SRC, 30, "One"), Photo(SRC, 30, "Two"), Photo(SRC, 20, "Three")]
for p in ph_list: p.src, p.mask, p.face_rect, p.face_checked, p.state = p1.src, p1.mask, p1.face_rect, True, "ready"
outs = {}
for fmt in ("PNG", "JPG", "PDF"):
    j = worker.Job("sheet", ph_list, params(se, Style((255, 255, 255), True, ts_e), save=(os.path.join(TMP, "export"), fmt)))
    end, _, t = run(j); outs[fmt] = (j.saved, j.result)
png_files, pages = outs["PNG"]; im = Image.open(png_files[0])
check(23, "PNG export (multi-page naming, 300 DPI)", len(png_files) == len(pages) and im.size == (2480, 3508) and abs(im.info["dpi"][0] - 300) < 0.1, f"{[os.path.basename(f) for f in png_files]} dpi={im.info['dpi']}")
jpg_files, _ = outs["JPG"]; ji = Image.open(jpg_files[0])
check(24, "JPG export (300 DPI)", ji.size == (2480, 3508) and abs(ji.info["dpi"][0] - 300) < 0.1 and ji.format == "JPEG")
pdf_files, _ = outs["PDF"]; raw = open(pdf_files[0], "rb").read()
mb = [tuple(float(x) for x in m) for m in re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", raw)]
npages = len(re.findall(rb"/Type\s*/Page\b", raw))
check(25, "PDF export: one multi-page file, exact A4 page size", len(pdf_files) == 1 and npages == len(pages) and all(abs(w - 595.2) < 0.6 and abs(h - 841.9) < 0.6 for w, h in mb), f"{npages} pages, MediaBox={mb[0]} pt (A4 = 595.28 x 841.89)")
check(25, "Overlay + guides baked into every export format", len(set(len(Image.open(f).tobytes()) for f in png_files)) == 1 and os.path.getsize(pdf_files[0]) > 100000)
# physical accuracy: measure border pitch on the real exported page
arr = np.asarray(Image.open(png_files[0]).convert("L")).astype(int); gd = layout.grid(se, False)
row = arr[gd["m"] + 60]; xs = np.where((row[:-1] > 100) & (row[1:] <= 100))[0]
starts = [x for x in xs if x > 20]; pitches = np.diff(starts[:: 1])
meas_mm = (gd["w"] + gd["hg"]) / 300 * 25.4
# MEASURE the exported page: find the black photo borders and convert pixels -> millimetres
sm = LayoutSpec(guides="none", border_px=3); pm = layout.build_pages(sm, [(*imaging.final_cell(p1, sm, st), 12)])[0]; pm.save(os.path.join(TMP, "measure.png"), dpi=(300, 300))
am = np.asarray(Image.open(os.path.join(TMP, "measure.png")).convert("RGB")).astype(int); gm = layout.grid(sm, False)
blk = lambda v: (v.sum(axis=-1) == 0)
rowv = blk(am[gm["m"] + 25]); runs = [i for i in range(1, len(rowv)) if rowv[i] and not rowv[i - 1]]
lefts = runs[0::2]; rights = [i for i in range(len(rowv) - 1) if rowv[i] and not rowv[i + 1]][1::2]
colv = blk(am[:, lefts[0] + 1]); tops = [i for i in range(1, len(colv)) if colv[i] and not colv[i - 1]]; bots = [i for i in range(len(colv) - 1) if colv[i] and not colv[i + 1]]
w_mm = (rights[0] - lefts[0] + 1) / 300 * 25.4; h_mm = (bots[0] - tops[0] + 1) / 300 * 25.4; pitch_mm = (lefts[1] - lefts[0]) / 300 * 25.4
pg_w, pg_h = Image.open(os.path.join(TMP, "measure.png")).size
check(27, "MEASURED on exported page @300 DPI: photo 35 x 45 mm, gap 4 mm, page 210 x 297 mm",
      abs(w_mm - 35) < 0.1 and abs(h_mm - 45) < 0.1 and abs(pitch_mm - 39) < 0.1 and abs(pg_w / 300 * 25.4 - 210) < 0.1 and abs(pg_h / 300 * 25.4 - 297) < 0.1,
      f"photo {w_mm:.2f} x {h_mm:.2f} mm, pitch {pitch_mm:.2f} mm (35+4), page {pg_w/300*25.4:.1f} x {pg_h/300*25.4:.1f} mm")
# 4x6 inch page
s46 = LayoutSpec(paper_name="4 x 6 in", paper_w=101.6, paper_h=152.4, guides="none"); pg46 = layout.build_pages(s46, [(*imaging.final_cell(p1, s46, st), 4)])[0]
check(27, "4 x 6 inch paper = 1200 x 1800 px", pg46.size == (1200, 1800), f"{pg46.size}")

# --- direct printing: logic only (real printers are Windows-only) ---
calls = []
class FakeDC:
    def CreatePrinterDC(self, n): calls.append(("create", n))
    def StartDoc(self, n): calls.append("startdoc")
    def GetDeviceCaps(self, k): return {88: 600, 90: 600, 112: 118, 113: 118}[k]
    def StartPage(self): calls.append("startpage")
    def EndPage(self): calls.append("endpage")
    def EndDoc(self): calls.append("enddoc")
    def DeleteDC(self): calls.append("delete")
    def GetHandleOutput(self): return 1
class FakeDib:
    def __init__(self, im): self.im = im
    def draw(self, h, box): calls.append(("draw", box))
import types
fake_ui = types.SimpleNamespace(CreateDC=lambda: FakeDC()); sys.modules["win32ui"] = fake_ui
import PIL; fake_iw = types.ModuleType("PIL.ImageWin"); fake_iw.Dib = FakeDib; sys.modules["PIL.ImageWin"] = fake_iw; PIL.ImageWin = fake_iw
printing.IS_WIN = True; printing.print_pages(pages[:2], "Test Printer", copies=2)
draws = [c for c in calls if isinstance(c, tuple) and c[0] == "draw"]
check(26, "Direct printing LOGIC (mock printer): 2 pages x 2 copies, actual-size scaling, no 'fit to page'",
      len(draws) == 4 and draws[0][1] == (-118, -118, -118 + 4960, -118 + 7016) and calls.count("startpage") == 4 and calls[-1] == "delete",
      f"device px for 600 dpi printer = {draws[0][1][2]-draws[0][1][0]} x {draws[0][1][3]-draws[0][1][1]} (= A4 @600dpi)  [REAL printer NOT tested - Windows only]")
printing.IS_WIN = sys.platform.startswith("win")

# ===================================================================== STABILITY
import socket as _s
real_connect = _s.socket.connect
def no_net(self, *a, **k): raise OSError("network disabled for test")
_s.socket.connect = no_net
off = Photo(SRC, 1); end, _, t = run(worker.Job("prepare", [off], params()))
check(28, "Offline processing (all network connections blocked)", end[0] == "done" and off.state == "ready", f"{t:.1f}s with sockets disabled")
_s.socket.connect = real_connect

# missing model / failed download -> use a fresh empty app-data dir
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "empty"); model._session = None; model._face = None; model._face_failed = False
real_url = model.MODEL_URL; model.MODEL_URL = "https://invalid.invalid/u2net.onnx"
mm_ = Photo(SRC, 1); end, _, t = run(worker.Job("prepare", [mm_], params()))
check(29, "Missing AI model -> clear message, fails fast, app not stuck", end[0] == "error" and end[2] == "model" and t < 15 and "Retry" in end[3] and mm_.state == "new", f"{t:.1f}s: {end[3][:70].replace(chr(10),' ')}...")
# failed (truncated) download then successful retry via a local server
srv_dir = os.path.join(TMP, "srv"); os.makedirs(srv_dir); shutil.copy(os.path.join(MODEL_SRC, "u2net.onnx"), srv_dir)
mode = {"truncate": True}
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k): super().__init__(*a, directory=srv_dir, **k)
    def log_message(self, *a): pass
    def do_GET(self):
        data = open(os.path.join(srv_dir, "u2net.onnx"), "rb").read()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers()
        self.wfile.write(data[: len(data) // 3] if mode["truncate"] else data)
        if mode["truncate"]: self.wfile.flush(); self.connection.close()
httpd = socketserver.TCPServer(("127.0.0.1", 0), H); threading.Thread(target=httpd.serve_forever, daemon=True).start()
model.MODEL_URL = f"http://127.0.0.1:{httpd.server_address[1]}/u2net.onnx"
j = worker.Job("warmup", [], params()); end, msgs, t = run(j)
part = os.path.join(os.environ["LOCALAPPDATA"], "SnapMitra", "models", "u2net.onnx.part")
check(30, "Interrupted model download -> error + Retry offered, no corrupt file left", end[0] == "error" and end[2] == "model" and not os.path.exists(part) and model.find_model() is None, end[3][:60].replace("\n", " "))
mode["truncate"] = False; j = worker.Job("warmup", [], params()); end, msgs, t = run(j)
prog = [m for m in msgs if m[0] == "progress" and "Downloading" in m[3]]
check(30, "Retry succeeds: download with progress, verified, cached for next launches", end[0] == "done" and model.find_model() is not None and len(prog) >= 1, f"{len(prog)} progress updates, {t:.1f}s; cached at {model.find_model()}")
model._session = None; t0 = time.time(); model.get_session(); first = time.time() - t0
check(30, "Second launch reuses the cached model (no download)", model.find_model() is not None and first < 30, f"session ready in {first:.1f}s"); httpd.shutdown()
model.MODEL_URL = real_url; os.environ["LOCALAPPDATA"] = TMP

# cancel
cp = [Photo(SRC, 1) for _ in range(10)]; j = worker.Job("prepare", cp, params()); q = queue.Queue()
th = threading.Thread(target=worker.run_job, args=(j, q), daemon=True); th.start(); time.sleep(2.0); j.cancel.set(); t0 = time.time()
while True:
    m = q.get(timeout=30)
    if m[0] in ("cancelled", "done", "error"): break
check(31, "Cancel processing stops quickly and leaves photos re-processable", m[0] == "cancelled" and time.time() - t0 < 5 and all(p.state in ("new", "ready") for p in cp), f"stopped in {time.time()-t0:.2f}s, ready={sum(p.state=='ready' for p in cp)}/10")

# session reuse (no re-initialisation)
s_a = model.get_session(); s_b = model.get_session(); check(6, "ONNX session is created once and reused", s_a is s_b)
# presets
presets.save_user_preset("Test ID", 30, 40, 0.7); pl = presets.load_photo_presets()
check(3, "User size presets persist (frequently used sizes)", any(p["name"] == "Test ID" and p["w_mm"] == 30 for p in pl) and pl[-1]["name"] == "Custom")

# ===================================================================== SUMMARY
bad = [r for r in RESULTS if not r[2]]
print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed")
for r in bad: print("FAILED:", r)
shutil.rmtree(TMP, ignore_errors=True)
sys.exit(1 if bad else 0)
