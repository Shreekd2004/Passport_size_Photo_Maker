import os, sys, time, queue, shutil, threading, logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
tmp = "/tmp/ppm_test"; shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
os.environ["LOCALAPPDATA"] = tmp
import model, worker, imaging, layout
from layout import LayoutSpec

def run(job):
    q = queue.Queue(); t=time.time()
    th = threading.Thread(target=worker.run_job, args=(job,q), daemon=True); th.start()
    stages=[]; end=None
    while True:
        m = q.get(timeout=300)
        if m[0]=="progress":
            if not stages or stages[-1][0]!=m[3]: stages.append((m[3], round(m[2])))
        elif m[0] in ("done","cancelled","error"): end=m; break
    print(f"  -> {end[0]} {end[2:] if end[0]=='error' else ''} in {time.time()-t:.1f}s")
    print("  stages:", stages)
    return end

spec = LayoutSpec()
src = "/mnt/user-data/uploads/1000517351.png"

print("== 1. OFFLINE first run (no model anywhere, bad URL) -> must fail FAST with a clear message")
model.MODEL_URL = "https://invalid.example.invalid/u2net.onnx"
j = worker.Job("prepare", [imaging.Photo(src)], dict(mode="ai", spec=spec, bg=(255,255,255)))
e = run(j); print("  message:", e[3][:160].replace("\n"," "))
assert e[0]=="error" and e[2]=="model"

print("== 2. Real download with progress (one time), then cached")
model.MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
j = worker.Job("warmup", [], dict(mode="ai", spec=spec, bg=(255,255,255)))
run(j)
print("  cached at:", model.find_model())

print("== 3. Cancel during processing")
photos=[imaging.Photo(src) for _ in range(6)]
j = worker.Job("prepare", photos, dict(mode="ai", spec=spec, bg=(255,255,255)))
q=queue.Queue(); th=threading.Thread(target=worker.run_job,args=(j,q),daemon=True); th.start()
time.sleep(2.5); j.cancel.set()
while True:
    m=q.get(timeout=30)
    if m[0] in("cancelled","done","error"): print("  ->",m[0]); break
print("  photo states:", [p.state for p in photos])

print("== 4. Multi-photo job: copies 8 / 12 / 5, save PNG + PDF")
photos=[imaging.Photo(src,8), imaging.Photo(src,12), imaging.Photo(src,5)]
out=os.path.join(tmp,"sheet.png")
j = worker.Job("sheet", photos, dict(mode="ai", spec=spec, bg=(255,255,255), save=(out,"PNG")))
run(j); print("  saved:", j.saved, "pages:", len(j.result), j.result[0].size)
j2 = worker.Job("sheet", photos, dict(mode="ai", spec=spec, bg=(255,255,255), save=(os.path.join(tmp,"sheet"),"PDF")))
run(j2); print("  saved:", j2.saved)
print("  2nd run reused cached cut-outs (no AI) - see time above")
j.result[0].save("/home/claude/test_sheet.png")
print("photo geometry:", photos[0].face)

print("== 5. Layout maths")
for name,w,h in [("A4",210,297),("A5",148,210),("4x6",101.6,152.4)]:
    s=LayoutSpec(paper_name=name,paper_w=w,paper_h=h)
    n,land,g=layout.choose(s,[8,12,5]); print(f"  {name}: {g['cols']}x{g['rows']} per page, landscape={land}, pages for 25 photos={n}")
s=LayoutSpec(photo_w=50.8,photo_h=50.8); n,land,g=layout.choose(s,[4]); print("  US 2x2 on A4:",g['cols'],"x",g['rows'])
try: layout.choose(LayoutSpec(paper_w=40,paper_h=50),[1])
except layout.LayoutError as e: print("  too-small paper ->", str(e)[:70])
s=LayoutSpec(); items=[(imaging.Image.new("RGB",(413,531),"gray"),c) for c in (30,30,5)]
print("  65 photos, new-row mode ->", len(layout.build_pages(s,items)),"pages;", end=" ")
s.new_row=False; print("compact ->", len(layout.build_pages(s,items)),"pages")
