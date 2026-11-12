"""Android feasibility: measure the background-removal / face models (size, memory, speed, mask quality).
Run on the DESKTOP as a proxy:  python tools/benchmark_models.py <models_dir> <portrait1> [<portrait2> ...]
Phone CPUs are slower than a desktop core - use the numbers to compare models, not as phone timings.
Creates the int8 / ORT-format variants next to the models. Prints a markdown table + writes docs/android_feasibility_results.json."""
import json, os, resource, statistics, subprocess, sys, time
import numpy as np
from PIL import Image

MEAN, STD = np.array((0.485, 0.456, 0.406), np.float32), np.array((0.229, 0.224, 0.225), np.float32)


def prep(img):
    a = np.asarray(img.convert("RGB").resize((320, 320), Image.LANCZOS), dtype=np.float32)
    a = a / max(float(a.max()), 1e-6)
    return ((a - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)


def hwm_mb():
    """Peak resident memory of THIS process from /proc (ru_maxrss would inherit the parent's peak after fork)."""
    for line in open("/proc/self/status"):
        if line.startswith("VmHWM"):
            return int(line.split()[1]) / 1024.0
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def child(path, threads):
    """Runs in its own process so peak memory is clean."""
    import onnxruntime as ort
    base = hwm_mb()
    so = ort.SessionOptions(); so.intra_op_num_threads = threads; so.log_severity_level = 3
    t = time.time(); s = ort.InferenceSession(path, sess_options=so, providers=["CPUExecutionProvider"]); load = time.time() - t
    after_load = hwm_mb()
    name = s.get_inputs()[0].name; shape = [d if isinstance(d, int) else 1 for d in s.get_inputs()[0].shape]
    x = np.random.rand(*shape).astype(np.float32)
    s.run(None, {name: x}); ts = []
    for _ in range(5):
        t = time.time(); s.run(None, {name: x}); ts.append(time.time() - t)
    print(json.dumps(dict(load_s=load, infer_ms=statistics.median(ts) * 1000, base_mb=base, load_mb=after_load - base, peak_mb=hwm_mb() - base)))


def mask_of(path, img):
    import onnxruntime as ort
    s = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    p = s.run(None, {s.get_inputs()[0].name: prep(img)})[0][:, 0]
    p = np.squeeze((p - p.min()) / max(float(p.max() - p.min()), 1e-6))
    return np.asarray(Image.fromarray((p * 255).astype("uint8")).resize(img.size, Image.LANCZOS))


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(sys.argv[2], int(sys.argv[3])); sys.exit()
    mdir, imgs = sys.argv[1], [Image.open(p).convert("RGB") for p in sys.argv[2:]]
    full = os.path.join(mdir, "u2net.onnx")
    int8 = os.path.join(mdir, "u2net_int8.onnx")
    if not os.path.exists(int8):
        from onnxruntime.quantization import QuantType, quantize_dynamic
        quantize_dynamic(full, int8, weight_type=QuantType.QUInt8)
    models = {"u2net fp32 (current)": full, "u2net int8 (dynamic quant.)": int8, "u2netp fp32 (small)": os.path.join(mdir, "u2netp.onnx"),
              "face detector (RFB-320)": os.path.join(mdir, "face_detector.onnx")}
    ref = [mask_of(full, im) for im in imgs]
    out = {}
    for name, path in models.items():
        row = dict(size_mb=os.path.getsize(path) / 1e6)
        for th in (1, 4):
            r = json.loads(subprocess.run([sys.executable, __file__, "--child", path, str(th)], capture_output=True, text=True).stdout.strip().splitlines()[-1])
            row[f"infer_ms_{th}t"] = r["infer_ms"]
            if th == 1: row["load_s"], row["load_mb"], row["peak_mb"] = r["load_s"], r["load_mb"], r["peak_mb"]
        if "face" not in name:
            m = [mask_of(path, im) for im in imgs]
            row["iou_vs_fp32"] = float(np.mean([((a > 127) & (b > 127)).sum() / max(1, ((a > 127) | (b > 127)).sum()) for a, b in zip(m, ref)]))
            row["mae_vs_fp32"] = float(np.mean([np.abs(a.astype(int) - b.astype(int)).mean() for a, b in zip(m, ref)]))
        out[name] = row
    print("| model | size MB | load s | RAM after load MB | peak RAM MB | infer ms (1 thread) | infer ms (4 threads) | mask IoU vs fp32 | mean abs diff |\n|---|---|---|---|---|---|---|---|---|")
    for n, r in out.items():
        print(f"| {n} | {r['size_mb']:.1f} | {r['load_s']:.2f} | {r['load_mb']:.0f} | {r['peak_mb']:.0f} | {r['infer_ms_1t']:.0f} | {r['infer_ms_4t']:.0f} | "
              f"{r.get('iou_vs_fp32', float('nan')):.3f} | {r.get('mae_vs_fp32', float('nan')):.2f} |")
    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "android_feasibility_results.json"), "w"), indent=1)
