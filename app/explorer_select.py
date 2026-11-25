"""Select a Unicode file path using the Windows Shell API."""
import ctypes
from ctypes import wintypes

def select_file(path):
    ole = ctypes.OleDLL('ole32')
    shell = ctypes.OleDLL('shell32')
    ole.CoInitialize.argtypes = [ctypes.c_void_p]
    ole.CoInitialize.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    shell.SHParseDisplayName.argtypes = [wintypes.LPCWSTR, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    shell.SHParseDisplayName.restype = ctypes.c_long
    shell.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
    shell.SHOpenFolderAndSelectItems.restype = ctypes.c_long
    ole.CoInitialize(None)
    item = ctypes.c_void_p()
    attributes = wintypes.DWORD()
    try:
        shell.SHParseDisplayName(str(path), None, ctypes.byref(item), 0, ctypes.byref(attributes))
        shell.SHOpenFolderAndSelectItems(item, 0, None, 0)
    finally:
        if item: ole.CoTaskMemFree(item)
        ole.CoUninitialize()
