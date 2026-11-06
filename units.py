"""Unit helpers. All print output is rendered at DPI pixels per inch (300 = photo-lab standard)."""
DPI = 300
MM_PER_INCH = 25.4


def mm_to_px(mm, dpi=DPI):
    return int(round(float(mm) / MM_PER_INCH * dpi))


def to_mm(value, unit):
    """Convert a value typed in 'mm' or 'in' to millimetres."""
    return float(value) * (MM_PER_INCH if unit == "in" else 1.0)


def from_mm(mm, unit):
    return float(mm) / (MM_PER_INCH if unit == "in" else 1.0)
