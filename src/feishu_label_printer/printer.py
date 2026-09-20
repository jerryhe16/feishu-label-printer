"""Windows RAW spooler; no printer-global calibration settings are changed."""
import ctypes
import os
from ctypes import wintypes as w


def send_raw(printer, raw, title):
    if os.name != "nt":
        raise RuntimeError("Actual printing is supported on Windows only")
    dll = ctypes.WinDLL("winspool.drv", use_last_error=True)

    class Doc(ctypes.Structure):
        _fields_ = [("name", w.LPWSTR), ("output", w.LPWSTR), ("datatype", w.LPWSTR)]

    signatures = {
        "OpenPrinterW": ([w.LPWSTR, ctypes.POINTER(w.HANDLE), w.LPVOID], w.BOOL),
        "StartDocPrinterW": ([w.HANDLE, w.DWORD, ctypes.POINTER(Doc)], w.DWORD),
        "StartPagePrinter": ([w.HANDLE], w.BOOL),
        "EndPagePrinter": ([w.HANDLE], w.BOOL),
        "EndDocPrinter": ([w.HANDLE], w.BOOL),
        "ClosePrinter": ([w.HANDLE], w.BOOL),
        "AbortPrinter": ([w.HANDLE], w.BOOL),
        "WritePrinter": ([w.HANDLE, w.LPVOID, w.DWORD, ctypes.POINTER(w.DWORD)], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(dll, name)
        function.argtypes, function.restype = args, result

    def check(result):
        if not result:
            raise ctypes.WinError(ctypes.get_last_error())
        return result

    handle = w.HANDLE()
    check(dll.OpenPrinterW(printer, ctypes.byref(handle), None))
    started = False
    try:
        job = check(dll.StartDocPrinterW(handle, 1, ctypes.byref(Doc(title, None, "RAW"))))
        started = True
        check(dll.StartPagePrinter(handle))
        written = w.DWORD()
        buffer = ctypes.create_string_buffer(raw)
        check(dll.WritePrinter(handle, buffer, len(raw), ctypes.byref(written)))
        if written.value != len(raw):
            raise RuntimeError("Only part of the label was accepted by the spooler")
        check(dll.EndPagePrinter(handle))
        check(dll.EndDocPrinter(handle))
        started = False
        return job
    finally:
        if started:
            dll.AbortPrinter(handle)
        dll.ClosePrinter(handle)
