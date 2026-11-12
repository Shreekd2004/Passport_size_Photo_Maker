"""Golden test vectors for porting SnapMitra's logic to another platform (Android/Kotlin).
The Python code is the REFERENCE implementation; a port must reproduce these numbers exactly.
Run:  python tools/make_parity_vectors.py        -> docs/parity_vectors.json
(tests/run_tests.py checks the file is up to date.)"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import imaging, layout, presets, textoverlay, units
from layout import LayoutSpec
from textoverlay import TextStyle


def build():
    v = {"note": "Reference outputs of the Python implementation (300 DPI). Positions are (row, col, photo_index)."}
    v["units"] = [dict(mm=m, px=units.mm_to_px(m)) for m in (1, 5, 25, 35, 45, 50.8, 101.6, 127, 148, 152.4, 177.8, 210, 297)] + \
                 [dict(inch=i, mm=units.to_mm(i, "in")) for i in (1, 1.5, 2, 4, 5, 6, 7)]
    v["photo_presets"] = [dict(name=p["name"], w_mm=p["w_mm"], h_mm=p["h_mm"], head_ratio=p["head_ratio"]) for p in presets.PHOTO_PRESETS]
    v["papers"] = [dict(name=n, w_mm=w, h_mm=h) for n, w, h in presets.PAPERS if w]
    grids = []
    for paper in [p for p in presets.PAPERS if p[1]]:
        for pr in [p for p in presets.PHOTO_PRESETS if p["name"] != "Custom"][:4]:
            for guides in ("none", "thin"):
                for cap in (0.0, 6.5):
                    sp = LayoutSpec(photo_w=pr["w_mm"], photo_h=pr["h_mm"], paper_name=paper[0], paper_w=paper[1], paper_h=paper[2],
                                    guides=guides, caption_mm=cap)
                    inp = dict(photo_w=sp.photo_w, photo_h=sp.photo_h, paper_w=sp.paper_w, paper_h=sp.paper_h, margin=sp.margin,
                               hgap=sp.hgap, vgap=sp.vgap, guides=guides, caption_mm=cap)
                    for land in (False, True):
                        grids.append(dict(input=inp, landscape=land, grid=layout.grid(sp, land)))
    v["grids"] = grids
    fills = []
    for cols, rows, counts, group in [(5, 5, [5], False), (5, 5, [4, 1], False), (5, 10, [4, 1, 8, 3], False), (5, 10, [4, 1, 8, 3], True),
                                      (5, 5, [6, 3, 7, 11, 1, 2, 9, 2, 6, 10], False), (5, 5, [6, 3, 7, 11, 1, 2, 9, 2, 6, 10], True),
                                      (7, 10, [30, 1, 0, 25], False), (2, 3, [4, 4, 4], True), (3, 2, [1], False)]:
        fills.append(dict(cols=cols, rows=rows, counts=counts, group=group, pages=layout.fill(cols, rows, counts, group)))
    v["fills"] = fills
    ch = []
    for counts, mode, orient in [([4, 1, 8], "continuous", "auto"), ([30, 30, 20], "group", "auto"), ([12], "continuous", "landscape")]:
        sp = LayoutSpec(mode=mode, orientation=orient)
        n, g, pages = layout.choose(sp, counts)
        ch.append(dict(counts=counts, mode=mode, orientation=orient, pages=n, landscape=g["landscape"], cols=g["cols"], rows=g["rows"]))
    v["choose"] = ch
    today = datetime.date(2026, 11, 6)
    cases = [TextStyle(enabled=True, use_name=True, use_date=True),
             TextStyle(enabled=True, use_name=True, name="Vishnu K D", use_dob=True, dob="15/08/2002", multiline=True),
             TextStyle(enabled=True, use_custom=True, custom="  Hello ", use_cdate=True, cdate="01/01/2030", use_date=True, date_mode="manual", date_text="02/02/2031"),
             TextStyle(enabled=False, use_name=True), TextStyle(enabled=True)]
    v["text"] = [dict(style=t.to_dict(), label="Ravi Kumar", today="2026-11-06", resolved=textoverlay.resolve_text(t, "Ravi Kumar", today),
                      n_lines=textoverlay.n_lines(t)) for t in cases]
    v["text_sizes"] = [dict(size_pt=s_, lines=n, caption_mm=textoverlay.caption_mm(TextStyle(enabled=True, position="below", size_pt=s_, multiline=n > 1, use_name=True, use_dob=True, dob="x", use_date=True)))
                       for s_ in (6, 8, 9, 12) for n in (1, 2)]
    v["fixed_mm"] = [dict(area_mm=a, photo_h=h, result=textoverlay.fixed_mm(TextStyle(enabled=True, position="fixed", area_mm=a), h))
                     for a, h in ((5, 45), (1, 45), (500, 45), (4, 25), (8, 50.8))]
    v["effective_head"] = [dict(head=hd, photo_h=h, area_mm=a, result=imaging.effective_head(LayoutSpec(head=hd, photo_h=h), TextStyle(enabled=True, position="fixed", area_mm=a)))
                           for hd, h, a in ((0.74, 45, 5), (0.62, 25, 4), (0.6, 50.8, 8), (0.9, 45, 12))]
    v["default_crop"] = [dict(geom=g, head_ratio=hr, aspect=asp, result=imaging.default_crop(g, hr, asp))
                         for g, hr, asp in ((dict(cx=632.0, top=162.0, chin=742.0), 0.74, 35 / 45), (dict(cx=300.0, top=60.0, chin=260.0), 0.62, 1.0),
                                            (dict(cx=500.0, top=100.0, chin=700.0), 0.83, 413 / 472))]
    v["fixed_canvas_px"] = [dict(w_mm=w, h_mm=h, area_mm=a, cell=[units.mm_to_px(w), units.mm_to_px(h)],
                                 photo_area_h=units.mm_to_px(h) - units.mm_to_px(textoverlay.fixed_mm(TextStyle(enabled=True, position="fixed", area_mm=a), h)),
                                 text_area_h=units.mm_to_px(textoverlay.fixed_mm(TextStyle(enabled=True, position="fixed", area_mm=a), h)))
                            for w, h, a in ((35, 45, 5), (25, 25, 4), (38.1, 50.8, 6), (50.8, 50.8, 8))]
    return v


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "parity_vectors.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    data = build()
    json.dump(data, open(out, "w"), indent=1)
    print("wrote", os.path.normpath(out), "-", {k: len(v) for k, v in data.items() if isinstance(v, list)})
