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


def device_size(page, dpi_x, dpi_y):
    """Pixels the page occupies on the printer so it prints at exactly its real size (300 DPI image)."""
    return int(round(page.width / DPI * dpi_x)), int(round(page.height / DPI * dpi_y))


def print_pages(pages, printer_name, doc_name="SnapMitra photos", copies=1):
    """Prints at 100% - no 'fit to page' scaling, so photos keep their physical dimensions."""
    if not IS_WIN:
        raise RuntimeError("Direct printing is available on Windows only. Save as PDF and print that instead.")
    import win32ui
    from PIL import ImageWin

    hdc = win32ui.CreateDC()
    hdc.CreatePrinterDC(printer_name)
    try:
        hdc.StartDoc(doc_name)
        dpi_x, dpi_y = hdc.GetDeviceCaps(88), hdc.GetDeviceCaps(90)      # LOGPIXELSX / Y
        off_x, off_y = hdc.GetDeviceCaps(112), hdc.GetDeviceCaps(113)    # PHYSICALOFFSETX / Y (unprintable edge)
        for _ in range(max(1, copies)):
            for pg in pages:
                if pg.width > pg.height:             # landscape sheet -> rotate so it feeds a portrait page
                    pg = pg.transpose(3)
                w, h = device_size(pg, dpi_x, dpi_y)
                hdc.StartPage()
                ImageWin.Dib(pg).draw(hdc.GetHandleOutput(), (-off_x, -off_y, -off_x + w, -off_y + h))
                hdc.EndPage()
        hdc.EndDoc()
    finally:
        hdc.DeleteDC()
