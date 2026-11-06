"""GUI tests (need a display: xvfb-run python tests/gui_tests.py). Drives the REAL window."""
import os, sys, time, shutil, traceback, json, tempfile
TMP = tempfile.mkdtemp(prefix="sm_gui_"); os.environ["LOCALAPPDATA"] = TMP
MODEL_SRC = os.environ.get("SM_MODEL_DIR", "/home/claude/models")
os.makedirs(os.path.join(TMP, "SnapMitra", "models")); [shutil.copy(os.path.join(MODEL_SRC, f), os.path.join(TMP, "SnapMitra", "models")) for f in os.listdir(MODEL_SRC) if f.endswith(".onnx")]
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import tkinter as tk
from tkinterdnd2 import TkinterDnD
import sv_ttk
root = TkinterDnD.Tk(); sv_ttk.set_theme("light")
import branding; branding.set_window_icon(root)
errors = []
root.report_callback_exception = lambda e, v, tb: (errors.append("".join(traceback.format_exception(e, v, tb))), print("TK ERROR", v))
import model, settings, presets
from app import App
a = App(root); root.deiconify()
R = []
def check(name, cond, detail=""): R.append(bool(cond)); print(f"[{'PASS' if cond else 'FAIL'}] {name}  {detail}")
def pump(sec):
    t = time.time()
    while time.time() - t < sec: root.update(); time.sleep(0.01)
def wait_idle(limit=240):
    t0 = time.time(); worst = 0.0; last = time.time()
    while (a.active or a.jobs) and time.time() - t0 < limit:
        root.update(); now = time.time(); worst = max(worst, now - last); last = now; time.sleep(0.005)
    return time.time() - t0, worst
def key(seq):
    root.focus_force(); root.update(); root.event_generate(seq); pump(0.15)

SRC = os.environ.get("SM_TEST_IMAGE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_portrait.png"); IN = os.path.join(TMP, "in"); os.makedirs(IN)
for n in ("Rahul_Sharma.png", "Priya_Nair.png", "Customer_Three.png", "D.png", "E.png", "F.png"): shutil.copy(SRC, os.path.join(IN, n))
el, worst = wait_idle(); check("Window opens, AI model warms up in the background", model.session_ready(), f"{el:.1f}s")
check("Window title + branding", root.title() == "SnapMitra \u2013 Your Smart Photo & Print Studio")
check("Dashboard shown first (on top); quick sizes built", a.content.winfo_children()[-1] is a.home and len(a.quick_row.winfo_children()) >= 4)
a.add_paths([IN]); el, worst = wait_idle()
check("RESPONSIVE: UI never froze while AI processed 6 photos", worst < 0.35 and all(p.state == "ready" for p in a.photos), f"worst freeze {worst*1000:.0f} ms during {el:.1f}s of processing")
check("Adding photos switches from the dashboard to the workspace", a.content.winfo_children()[-1] is a.workspace)
# copies + totals
for p, n in zip(a.photos, (8, 12, 5, 1, 1, 1)): p.copies = n
a.refresh_list(); a.update_info(); a.update_total()
check("Per-photo copy counts feed the total", "28 prints" in a.lbl_total.cget("text"), a.lbl_total.cget("text"))
# keyboard shortcuts
n0 = len(a.photos); a.select(a.photos[0]); key("<Control-d>"); check("Shortcut Ctrl+D duplicates", len(a.photos) == n0 + 1)
key("<Control-z>"); check("Shortcut Ctrl+Z undoes", len(a.photos) == n0)
key("<Control-y>"); check("Shortcut Ctrl+Y redoes", len(a.photos) == n0 + 1)
key("<Delete>"); check("Shortcut Delete removes the selected photo", len(a.photos) == n0)
key("<Control-Key-3>"); check("Shortcut Ctrl+3 opens Preview tab", a.nb.index(a.nb.select()) == 2)
key("<Control-g>"); wait_idle(); check("Shortcut Ctrl+G generates the sheet", a.pages_ok and len(a.pages) >= 1, f"{len(a.pages)} page(s)")
# reorder
first = a.photos[0]; a.move(first, 1); check("Reorder moves a photo", a.photos[1] is first); a.undo()
# layout: units / presets
a.set_preset("US Passport"); check("US Passport = 2 x 2 in = 50.8 mm", abs(a.spec().photo_w - 50.8) < 0.01 and a.g("photo_preset") == "US Passport")
a.V["unit"].set("in"); a.on_unit_change(); check("Switch to inches converts the numbers (50.8 mm -> 2.0 in)", abs(a.g("pw") - 2.0) < 0.001 and abs(a.spec().photo_w - 50.8) < 0.01, f"shows {a.g('pw')} in")
a.V["pw"].set(1.5); pump(0.1); check("Typing a size switches the preset box to 'Custom'", a.g("photo_preset") == "Custom" and abs(a.spec().photo_w - 38.1) < 0.01, f"1.5 in = {a.spec().photo_w:.1f} mm")
a.V["unit"].set("mm"); a.on_unit_change(); check("Back to millimetres converts again", abs(a.g("pw") - 38.1) < 0.01)
a.set_preset("Stamp Size"); check("Stamp Size preset is 25 x 25 mm", abs(a.spec().photo_w - 25) < 0.01 and abs(a.spec().photo_h - 25) < 0.01)
a.set_paper("5 x 7 in"); check("Paper preset 5 x 7 in", abs(a.spec().paper_w - 127) < 0.1)
a.set_paper("A4")
# save preset
import tkinter.simpledialog as sd; sd.askstring = lambda *k, **kw: "College ID"
a.V["pw"].set(30.0); a.V["ph"].set(40.0); pump(0.1); a.save_preset(); check("'Save as preset' adds a reusable size", "College ID" in a.preset_by_name and a.g("photo_preset") == "College ID")
# text overlay via UI variables
a.V["t_enabled"].set(True); a.V["t_source"].set("name"); a.sel = a.photos[0]; a.load_editor(); a.v_label.set("Mr. Test Name"); pump(0.1)
check("Customer-name entry edits the selected photo's label", a.photos[0].label == "Mr. Test Name")
a.V["t_pos"].set("below"); check("Switching text to 'below' reserves a strip in the layout", a.spec().caption_mm > 0, f"{a.spec().caption_mm} mm")
a.V["t_pos"].set("inside"); check("... and 'inside' reserves none", a.spec().caption_mm == 0)
# live preview renders w/ overlay (no exception)
a.nb.select(a.tab_edit); a.draw_editor(); check("Live preview draws with text overlay", a.ed_tk is not None and not errors)
# background removal toggle is instant
t0 = time.time(); a.V["remove_bg"].set(False); pump(0.2); w1 = time.time() - t0; a.V["remove_bg"].set(True); pump(0.2); wait_idle()
check("Toggle 'remove background' off/on re-uses the cached mask (instant)", all(p.state == "ready" for p in a.photos) and w1 < 1.5, f"{w1:.2f}s")
# autosave + continue session + project
a.autosave(); d = settings.read_autosave(); check("Auto-save writes the session", d is not None and len(d["photos"]) == len(a.photos))
pf = os.path.join(TMP, "p.snapmitra"); a.project_path = pf; a.save_project(); check("Save project + appears in Recent", os.path.isfile(pf) and pf in a.store.recent)
a.photos, a.sel = [], None; a.refresh_list(); a.continue_last_session(); wait_idle(); check("Continue last session restores photos, copies and edits", len(a.photos) == len(d["photos"]) and a.photos[0].label == "Mr. Test Name")
a.show_home(); pump(0.3); check("Home button returns to the dashboard and offers 'Continue last session'", a.content.winfo_children()[-1] is a.home and a.btn_continue.winfo_ismapped(), a.btn_continue.cget("text").strip())
# About / splash
a.show_about(); pump(0.4); tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]; check("About dialog opens", len(tops) >= 1); [t.destroy() for t in tops]
from ui_home import make_splash; sp = make_splash(root); check("Splash screen builds with the logo", sp.winfo_exists()); sp.destroy()
check("Window icon set", hasattr(root, "_icon_ref"))
check("No Tk callback exceptions during the whole session", not errors, "; ".join(e.splitlines()[-1] for e in errors)[:200])
print(f"\n{sum(R)}/{len(R)} GUI checks passed"); shutil.rmtree(TMP, ignore_errors=True); os._exit(0 if all(R) else 1)
