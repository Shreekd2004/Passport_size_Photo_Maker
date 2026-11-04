"""Direct printing to an installed Windows printer at true physical size (via pywin32)."""
import sys


from units import DPI

IS_WIN = sys.platform.startswith("win")


def list_printers():
    if not IS_WIN:
        return [], None
    import win32print

    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    names = [p[2] for p in win32print.EnumPrinters(flags)]
    try:
        default = win32print.GetDefaultPrinter()
    except Exception:
        default = names[0] if names else None
    return names, default


def print_pages(pages, printer_name, doc_name="Passport photos"):
    """Each page image is 300 DPI; scale by printer DPI so photos print at exactly their real size."""
    if not IS_WIN:
        raise RuntimeError("Direct printing is available on Windows only. Save as PDF and print that instead.")
    import win32ui
    from PIL import ImageWin

    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    try:
        hdc.StartDoc(doc_name)
        dpi_x = hdc.GetDeviceCaps(88)    # LOGPIXELSX
        dpi_y = hdc.GetDeviceCaps(90)    # LOGPIXELSY
        off_x = hdc.GetDeviceCaps(112)   # PHYSICALOFFSETX (non-printable edge)
        off_y = hdc.GetDeviceCaps(113)   # PHYSICALOFFSETY
        for pg in pages:
            if pg.width > pg.height:     # landscape sheet -> rotate so it feeds a portrait page
                pg = pg.transpose(3)     # ROTATE_90
            w = int(round(pg.width / DPI * dpi_x))
            h = int(round(pg.height / DPI * dpi_y))
            hdc.StartPage()
            ImageWin.Dib(pg).draw(hdc.GetHandleOutput(), (-off_x, -off_y, -off_x + w, -off_y + h))
            hdc.EndPage()
        hdc.EndDoc()
    finally:
        hdc.DeleteDC()
