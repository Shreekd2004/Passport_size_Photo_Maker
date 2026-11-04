"""Unit helpers. All print output is rendered at DPI pixels per inch."""
DPI = 300


def mm_to_px(mm, dpi=DPI):
    return int(round(float(mm) / 25.4 * dpi))
