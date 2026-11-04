"""Download the U2-Net model into ./models so it is bundled INSIDE the app (offline-first)."""
import hashlib, os, sys, urllib.request

URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
MD5 = "60024c5c889badc19c04ad937298a77b"
dest = os.path.join("models", "u2net.onnx")
os.makedirs("models", exist_ok=True)

for attempt in range(1, 4):
    try:
        print(f"download attempt {attempt}...")
        urllib.request.urlretrieve(URL, dest)
        h = hashlib.md5(open(dest, "rb").read()).hexdigest()
        if h == MD5:
            print("model OK", os.path.getsize(dest), "bytes")
            sys.exit(0)
        print("checksum mismatch", h)
    except Exception as e:
        print("failed:", e)
sys.exit("could not download model")
