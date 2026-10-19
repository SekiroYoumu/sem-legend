"""Exercise the actual Tk widgets and batch worker against repository samples."""
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'.vendor'))
from tkinterdnd2 import TkinterDnD
from semlegend.gui import App
from semlegend.samples import ORIGINAL_EXAMPLES


def pump(root, predicate, timeout=30):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        root.update()
        if predicate(): return
        time.sleep(.03)
    raise AssertionError('GUI operation timed out')


root=TkinterDnD.Tk()
app=App(root)
try:
    sample_count=len(list(ORIGINAL_EXAMPLES.glob('*.tif')))
    # Exercise the Tcl drop parser, including a name containing parentheses.
    class Drop: data = root.tk.call('list',str(ORIGINAL_EXAMPLES))
    app.drop(Drop())
    pump(root,lambda:len(app.items)==sample_count and all(app.items.values()))
    pump(root,lambda:len(app.photos)>0)
    assert len(app.tree.get_children())==sample_count
    missing=str((ORIGINAL_EXAMPLES/'200rpm31(1).tif').resolve())
    app.tree.selection_set(missing);app.select()
    assert app.scale_state(missing)=='自动识别'
    assert not app.items[missing].requires_confirmation
    app.show_recognition()
    root.update()
    import tkinter as tk
    dialogs=[widget for widget in root.winfo_children() if isinstance(widget,tk.Toplevel)]
    assert dialogs
    for dialog in dialogs: dialog.destroy()
    app.scale_var.set('159.5');app.apply_scale()
    assert app.scales[missing]==159.5
    app.preview_kind.set('并排对比');app.schedule_preview()
    pump(root,lambda:len(app.photos)==2)
    app.mode.set('框选裁剪');app.change_mode()
    pump(root,lambda:app.preview_kind.get()=='原始图像' and 'original' in app.transforms and len(app.photos)==1)
    # Use coordinate transform to select a real source ROI through the mouse handlers.
    ox,oy,sx,sy,w,h=app.transforms['original']
    class Event: pass
    start,end=Event(),Event()
    start.x,start.y=ox+50*sx,oy+50*sy
    end.x,end.y=ox+950*sx,oy+650*sy
    app.drag_start(start);app.drag_move(end);app.drag_end(end)
    assert app.custom_crops[missing]==(50,50,950,650)
    app.reset_crop()
    app.mode.set('查看');app.preview_kind.set('处理结果');app.schedule_preview()
    pump(root,lambda:len(app.photos)==1 and app.preview_report.get('calibration_source')=='手动输入')
    drag=app.drag_export(None)
    assert Path(drag[2][0]).is_file()
    app.output.set(str(ROOT/'validation_output'/'gui_batch'))
    app.export(True)
    pump(root,lambda:not app.exporting)
    assert len(app.last_exports)==sample_count
    files=list((ROOT/'validation_output'/'gui_batch').glob('*.csv'))
    with max(files,key=lambda p:p.stat().st_mtime).open(encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==sample_count and all(r['status']=='成功' for r in rows)
    print(f'GUI PASS: drop import, preview, calibration, crop interaction, drag export, batch {sample_count}/{sample_count}')
    # Capture this app's own window without requiring access to the desktop.
    try:
        import ctypes
        from ctypes import wintypes
        from PIL import Image
        root.update()
        hwnd=root.winfo_id()
        user=ctypes.windll.user32;gdi=ctypes.windll.gdi32
        user.GetDC.restype=wintypes.HDC
        gdi.CreateCompatibleDC.restype=wintypes.HDC
        gdi.CreateCompatibleBitmap.restype=wintypes.HBITMAP
        gdi.SelectObject.restype=wintypes.HGDIOBJ
        for fn,args in [(gdi.CreateCompatibleDC,[wintypes.HDC]),(gdi.CreateCompatibleBitmap,[wintypes.HDC,ctypes.c_int,ctypes.c_int]),
                        (gdi.SelectObject,[wintypes.HDC,wintypes.HGDIOBJ]),(gdi.DeleteDC,[wintypes.HDC]),
                        (gdi.DeleteObject,[wintypes.HGDIOBJ]),(user.PrintWindow,[wintypes.HWND,wintypes.HDC,wintypes.UINT]),
                        (user.ReleaseDC,[wintypes.HWND,wintypes.HDC])]:fn.argtypes=args
        w,h=root.winfo_width(),root.winfo_height()
        dc=user.GetDC(hwnd);mem=gdi.CreateCompatibleDC(dc);bmp=gdi.CreateCompatibleBitmap(dc,w,h)
        previous=gdi.SelectObject(mem,bmp)
        class Header(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('width',wintypes.LONG),('height',wintypes.LONG),('planes',wintypes.WORD),('bits',wintypes.WORD),('compression',wintypes.DWORD),('image_size',wintypes.DWORD),('xppm',wintypes.LONG),('yppm',wintypes.LONG),('used',wintypes.DWORD),('important',wintypes.DWORD)]
        header=Header(ctypes.sizeof(Header),w,-h,1,32,0,0,0,0,0,0)
        data=ctypes.create_string_buffer(w*h*4)
        user.PrintWindow(hwnd,mem,3)
        gdi.GetDIBits.argtypes=[wintypes.HDC,wintypes.HBITMAP,wintypes.UINT,wintypes.UINT,ctypes.c_void_p,ctypes.c_void_p,wintypes.UINT]
        gdi.SelectObject(mem,previous)
        result=gdi.GetDIBits(mem,bmp,0,h,data,ctypes.byref(header),0)
        if result:
            Image.frombuffer('RGB',(w,h),data.raw,'raw','BGRX',0,1).save(ROOT/'validation_output'/'gui_preview.png')
        gdi.DeleteObject(bmp);gdi.DeleteDC(mem);user.ReleaseDC(hwnd,dc)
    except Exception as e: print('Window capture unavailable:',str(e))
finally:
    app.close()
