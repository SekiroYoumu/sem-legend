"""Copy an image to the Windows clipboard without additional dependencies."""
import ctypes
import io
import os
import time
from ctypes import wintypes


def copy_image(image, owner=None):
    if os.name != 'nt':
        raise OSError('图片剪贴板功能目前支持 Windows。')
    with io.BytesIO() as buffer:
        image.convert('RGB').save(buffer, format='BMP')
        # CF_DIB contains the bitmap information and pixels, without the BMP file header.
        dib = buffer.getvalue()[14:]

    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalUnlock.restype = wintypes.BOOL
    kernel.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel.GlobalFree.restype = wintypes.HGLOBAL
    user.OpenClipboard.argtypes = [wintypes.HWND]
    user.OpenClipboard.restype = wintypes.BOOL
    user.EmptyClipboard.argtypes = []
    user.EmptyClipboard.restype = wintypes.BOOL
    user.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user.SetClipboardData.restype = wintypes.HANDLE
    user.CloseClipboard.argtypes = []
    user.CloseClipboard.restype = wintypes.BOOL

    handle = kernel.GlobalAlloc(0x0002, len(dib))  # GMEM_MOVEABLE
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    opened = False
    transferred = False
    try:
        pointer = kernel.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            ctypes.memmove(pointer, dib, len(dib))
        finally:
            kernel.GlobalUnlock(handle)
        for attempt in range(10):
            if user.OpenClipboard(owner):
                opened = True
                break
            if attempt < 9:
                time.sleep(.03)
        if not opened:
            raise OSError('剪贴板正被其他程序占用，请稍后重试。')
        if not user.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())
        if not user.SetClipboardData(8, handle):  # CF_DIB
            raise ctypes.WinError(ctypes.get_last_error())
        transferred = True  # Windows now owns the allocation, including after app exit.
    finally:
        if opened:
            user.CloseClipboard()
        if not transferred:
            kernel.GlobalFree(handle)
