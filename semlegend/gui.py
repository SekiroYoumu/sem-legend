from __future__ import annotations

import copy
import csv
import json
import math
import os
import queue
import tempfile
import threading
import tkinter as tk
from dataclasses import asdict, fields
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageOps, ImageTk
from . import __version__

from .core import EXTENSIONS, ROOT, Settings, analyze, export_image, load_image, render

try:
    from tkinterdnd2 import COPY, DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(f'SEM Legend {__version__} · 本地图像整理')
        self.root.geometry('1320x870')
        self.root.minsize(1050, 720)
        self.events = queue.Queue()
        self.items = {}
        self.current = None
        self.settings = Settings()
        self.custom_crops = {}
        self.scales = {}
        self.photos = []
        self.last_exports = {}
        self.drag_temp = tempfile.TemporaryDirectory(prefix='semlegend-drag-')
        self.exporting = False
        self.cancel = threading.Event()
        self.revision = 0
        self.preview_pending = None
        self.mode = tk.StringVar(value='查看')
        self.status = tk.StringVar(value='拖入图像或文件夹开始。所有处理均在本机完成。')
        self.detail = tk.StringVar(value='尚未选择图像')
        self.output = tk.StringVar(value=str(ROOT / 'output'))
        self.scale_var = tk.StringVar()
        self.cal_length = tk.StringVar(value='10')
        self.cal_unit = tk.StringVar(value='µm')
        self.preview_kind = tk.StringVar(value='处理结果')
        self.vars = {}
        self.transforms = {}
        self.selection = None
        self._build()
        self.root.after(100, self._poll)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.bind('<Control-o>', lambda e: self.add_files())
        self.root.bind('<Control-s>', lambda e: self.export(False))
        self.root.bind('<Delete>', lambda e: self.remove() if self.root.focus_get() == self.tree else None)

    def _build(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TButton', padding=(9, 6))
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 17, 'bold'))
        style.configure('Treeview', rowheight=30, font=('Microsoft YaHei UI', 10))
        top = ttk.Frame(self.root, padding=(16, 12))
        top.pack(fill='x')
        ttk.Label(top, text='SEM Legend', style='Title.TLabel').pack(side='left')
        ttk.Label(top, text='  裁剪 · 调色 · 标尺', foreground='#666666').pack(side='left')
        for text, command in [('添加图像', self.add_files), ('添加文件夹', self.add_folder), ('载入样例', lambda: self.add_paths([ROOT / 'example']))]:
            ttk.Button(top, text=text, command=command).pack(side='left', padx=5)
        ttk.Button(top, text='保存预设', command=self.save_preset).pack(side='right', padx=4)
        ttk.Button(top, text='读取预设', command=self.load_preset).pack(side='right')

        body = ttk.Panedwindow(self.root, orient='horizontal')
        body.pack(fill='both', expand=True, padx=12)
        left = ttk.Frame(body, width=265)
        middle = ttk.Frame(body)
        right = ttk.Frame(body, width=310)
        body.add(left, weight=0)
        body.add(middle, weight=1)
        body.add(right, weight=0)
        ttk.Label(left, text='图像队列 · 可拖入文件或文件夹', padding=6).pack(anchor='w')
        self.tree = ttk.Treeview(left, columns=('state',), show='tree headings', selectmode='extended', height=16)
        self.tree.heading('#0', text='文件名')
        self.tree.heading('state', text='尺度')
        self.tree.column('#0', width=165, minwidth=95)
        self.tree.column('state', width=85, minwidth=70)
        self.tree.pack(fill='both', expand=True)
        self.tree.tag_configure('warn', foreground='#b56a00')
        self.tree.tag_configure('error', foreground='#ba3434')
        self.tree.bind('<<TreeviewSelect>>', self.select)
        ttk.Button(left, text='移除选中', command=self.remove).pack(fill='x', pady=6)
        ttk.Label(left, text='元数据 / 自动识别：可直接导出\n需核对：存在歧义或尺度冲突\n批量导出默认处理队列中的全部图像', wraplength=245, foreground='#666666').pack(anchor='w', pady=4)

        preview_top = ttk.Frame(middle)
        preview_top.pack(fill='x', pady=5)
        ttk.Label(preview_top, text='预览').pack(side='left', padx=8)
        for label in ('处理结果', '原始图像', '并排对比'):
            ttk.Radiobutton(preview_top, text=label, variable=self.preview_kind, value=label,
                            command=self.schedule_preview).pack(side='left', padx=4)
        self.canvas = tk.Canvas(middle, bg='#24282e', highlightthickness=0)
        self.canvas.pack(fill='both', expand=True, padx=6)
        self.canvas.bind('<Configure>', lambda e: self.schedule_preview())
        self.canvas.bind('<ButtonPress-1>', self.drag_start)
        self.canvas.bind('<B1-Motion>', self.drag_move)
        self.canvas.bind('<ButtonRelease-1>', self.drag_end)
        self.canvas.bind('<MouseWheel>', self.zoom)
        self.zoom_factor = 1.0
        self.canvas.create_text(230, 200, text='拖入 SEM 图像\n或点击「载入样例」', fill='#bfc7d1', font=('Microsoft YaHei UI', 18), justify='center')
        ttk.Label(middle, textvariable=self.detail, wraplength=620, padding=8).pack(fill='x')

        notebook = ttk.Notebook(right)
        notebook.pack(fill='both', expand=True, padx=5)
        def scroll_tab(title):
            page = ttk.Frame(notebook)
            notebook.add(page, text=title)
            canvas = tk.Canvas(page, highlightthickness=0, width=300, bg='#dcdad5')
            scrollbar = ttk.Scrollbar(page, orient='vertical', command=canvas.yview)
            canvas.configure(yscrollcommand=scrollbar.set)
            scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            content = ttk.Frame(canvas,padding=10)
            win = canvas.create_window((0,0),window=content,anchor='nw')
            content.bind('<Configure>',lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
            canvas.bind('<Configure>',lambda e: canvas.itemconfigure(win,width=e.width))
            return content
        image_tab, scale_tab, file_tab = (scroll_tab(title) for title in ('图像','标尺','导出'))

        self.check(image_tab, 'auto_crop', '自动裁掉底部信息栏')
        ttk.Label(image_tab, text='鼠标操作（使用原始图像视图）').pack(anchor='w', pady=(12, 4))
        for mode in ('查看', '框选裁剪', '画线校准'):
            ttk.Radiobutton(image_tab, text=mode, value=mode, variable=self.mode, command=self.change_mode).pack(anchor='w')
        ttk.Button(image_tab, text='清除当前手动裁剪', command=self.reset_crop).pack(fill='x', pady=6)
        self.combo(image_tab, 'tone', '亮度统一方式', ['逐图自动', '固定黑白场', '保留原始'])
        self.number(image_tab, 'low', '自动黑场百分位', 0, 25, .1)
        self.number(image_tab, 'high', '自动白场百分位', 75, 100, .1)
        self.number(image_tab, 'black', '固定黑场 (0–255)', 0, 254, 1)
        self.number(image_tab, 'white', '固定白场 (0–255)', 1, 255, 1)
        self.slider(image_tab, 'brightness', '亮度', -100, 100)
        self.slider(image_tab, 'contrast', '对比度', .2, 3)
        self.slider(image_tab, 'gamma', 'Gamma（>1 提亮）', .2, 3)
        ttk.Button(image_tab, text='重置全局图像参数', command=self.reset_tone).pack(fill='x', pady=8)

        self.check(scale_tab, 'add_bar', '添加标尺（未校准时禁止导出标尺）')
        ttk.Label(scale_tab, text='当前图像像素尺寸 · nm/像素').pack(anchor='w', pady=(12, 3))
        entry = ttk.Entry(scale_tab, textvariable=self.scale_var)
        entry.pack(fill='x')
        ttk.Button(scale_tab, text='应用到当前图像', command=self.apply_scale).pack(fill='x', pady=4)
        ttk.Button(scale_tab, text='恢复自动尺度', command=self.reset_scale).pack(fill='x', pady=2)
        ttk.Button(scale_tab, text='查看自动识别依据', command=self.show_recognition).pack(fill='x', pady=4)
        ttk.Separator(scale_tab).pack(fill='x', pady=10)
        ttk.Label(scale_tab, text='画线校准：先输入原标尺长度，\n再切换「画线校准」连接原标尺两端。', wraplength=270).pack(anchor='w')
        row = ttk.Frame(scale_tab); row.pack(fill='x', pady=5)
        ttk.Entry(row, textvariable=self.cal_length, width=12).pack(side='left')
        ttk.Combobox(row, textvariable=self.cal_unit, values=['nm', 'µm', 'mm'], width=6, state='readonly').pack(side='left', padx=5)
        self.number(scale_tab, 'bar_nm', '新标尺长度 · nm（0=自动）', 0, 1e10, 1000)
        self.number(scale_tab, 'auto_bar_min_ratio', '自动最小长度 / 图宽', .01, .5, .01)
        self.combo(scale_tab, 'corner', '标尺位置', ['左下', '右下', '左上', '右上'])
        self.combo(scale_tab, 'color', '颜色', ['白色', '黑色'])
        self.number(scale_tab, 'font_ratio', '字号 / 图高', .01, .15, .005)
        self.number(scale_tab, 'thickness_ratio', '线宽 / 图高', .002, .06, .002)
        self.number(scale_tab, 'margin_ratio', '边距 / 图像短边', .01, .25, .005)
        self.check(scale_tab, 'outline', '文字及标尺描边')

        ttk.Label(file_tab, text='输出文件夹').pack(anchor='w')
        ttk.Entry(file_tab, textvariable=self.output).pack(fill='x', pady=5)
        ttk.Button(file_tab, text='选择输出文件夹', command=self.choose_output).pack(fill='x')
        self.combo(file_tab, 'output_format', '无损格式', ['PNG', 'TIFF'])
        self.number(file_tab, 'output_width', '输出宽度 · px（0=原尺寸）', 0, 16384, 128)
        ttk.Label(file_tab, text='每张图同时保存 JSON 处理记录。\n同名文件自动编号，不覆盖原图。\nTIFF 会写入输出像素尺寸。', wraplength=270, foreground='#666666').pack(anchor='w', pady=14)
        ttk.Button(file_tab, text='导出当前图像', command=lambda: self.export(False)).pack(fill='x', pady=5)
        ttk.Button(file_tab, text='复制当前图片到剪贴板', command=self.copy_current_image).pack(fill='x', pady=5)
        ttk.Button(file_tab, text='批量导出全部', command=lambda: self.export(True)).pack(fill='x', pady=5)
        ttk.Button(file_tab, text='取消批处理', command=self.cancel.set).pack(fill='x', pady=5)
        self.drag_button = ttk.Label(file_tab, text='↗ 按住这里拖出当前结果', anchor='center', relief='groove', padding=10)
        self.drag_button.pack(fill='x', pady=14)
        ttk.Button(file_tab, text='打开输出文件夹', command=self.open_output).pack(fill='x')
        ttk.Label(file_tab, text='参数默认作用于整批；\n手动尺度和裁剪仅作用于当前图像。\n滚轮可放大预览。', foreground='#666666').pack(anchor='w', pady=15)

        bottom = ttk.Frame(self.root, padding=(14, 8))
        bottom.pack(fill='x')
        self.progress = ttk.Progressbar(bottom, length=150, mode='determinate')
        self.progress.pack(side='right')
        ttk.Label(bottom, textvariable=self.status).pack(side='left', fill='x', expand=True)
        if TkinterDnD:
            for widget in (self.root, self.tree, self.canvas):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', self.drop)
            self.drag_button.drag_source_register(1, DND_FILES)
            self.drag_button.dnd_bind('<<DragInitCmd>>', self.drag_export)
        else:
            self.drag_button.configure(text='拖拽组件未安装，可使用导入/导出按钮')

    def check(self, parent, key, text):
        v = tk.BooleanVar(value=getattr(self.settings, key)); self.vars[key] = v
        ttk.Checkbutton(parent, text=text, variable=v, command=self.schedule_preview).pack(anchor='w', pady=5)

    def combo(self, parent, key, label, values):
        ttk.Label(parent, text=label).pack(anchor='w', pady=(9, 2))
        v = tk.StringVar(value=getattr(self.settings, key)); self.vars[key] = v
        w = ttk.Combobox(parent, textvariable=v, values=values, state='readonly')
        w.pack(fill='x'); w.bind('<<ComboboxSelected>>', lambda e: self.schedule_preview())

    def number(self, parent, key, label, low, high, step):
        row = ttk.Frame(parent); row.pack(fill='x', pady=4)
        ttk.Label(row, text=label).pack(side='left')
        v = tk.StringVar(value=str(getattr(self.settings, key))); self.vars[key] = v
        w = ttk.Spinbox(row, textvariable=v, from_=low, to=high, increment=step, width=9,
                        command=self.schedule_preview)
        w.pack(side='right'); w.bind('<Return>', lambda e: self.schedule_preview())
        w.bind('<FocusOut>', lambda e: self.schedule_preview())

    def slider(self, parent, key, label, low, high):
        row = ttk.Frame(parent); row.pack(fill='x', pady=(7, 0))
        ttk.Label(row, text=label).pack(side='left')
        v = tk.DoubleVar(value=getattr(self.settings, key)); self.vars[key] = v
        entry = ttk.Spinbox(row, textvariable=v, from_=low, to=high,
                            increment=.1, width=9, command=self.schedule_preview)
        entry.pack(side='right')
        entry.bind('<Return>', lambda e: self.schedule_preview())
        entry.bind('<FocusOut>', lambda e: self.schedule_preview())
        ttk.Scale(parent, variable=v, from_=low, to=high,
                  command=lambda value: self.schedule_preview()).pack(fill='x')

    def get_settings(self):
        result = Settings()
        for f in fields(result):
            raw = self.vars[f.name].get()
            default = getattr(result, f.name)
            if isinstance(default, bool): value = bool(raw)
            elif isinstance(default, str): value = str(raw)
            else:
                value = float(raw)
                if not math.isfinite(value): raise ValueError('参数必须是有限数字')
                # Float fields can have integer-valued defaults (e.g. gamma=1).
                # Only the declared integer field, output_width, needs rounding checks.
                if f.type is int or f.type == 'int':
                    if not value.is_integer(): raise ValueError('输出宽度必须是整数')
                    value = int(value)
            setattr(result, f.name, value)
        if not .005 <= result.font_ratio <= .2 or not .001 <= result.thickness_ratio <= .1 or not 0 <= result.margin_ratio <= .4:
            raise ValueError('字号、线宽或边距超出合理范围')
        if result.bar_nm < 0: raise ValueError('标尺长度不能为负数')
        return result

    def add_files(self):
        paths = filedialog.askopenfilenames(filetypes=[('图像', '*.tif *.tiff *.png *.jpg *.jpeg *.bmp'), ('所有文件', '*.*')])
        self.add_paths(paths)

    def add_folder(self):
        folder = filedialog.askdirectory()
        if folder: self.add_paths([folder])

    def drop(self, event):
        self.add_paths(self.root.tk.splitlist(event.data))
        return COPY

    def add_paths(self, paths):
        files = []
        for raw in paths:
            p = Path(raw).resolve()
            if p.is_dir(): files.extend(sorted(x for x in p.rglob('*') if x.is_file() and x.suffix.lower() in EXTENSIONS))
            elif p.is_file() and p.suffix.lower() in EXTENSIONS: files.append(p)
        fresh = []
        for p in files:
            key = str(p)
            if key in self.items: continue
            self.items[key] = None
            self.tree.insert('', 'end', iid=key, text=p.name, values=('读取中',))
            fresh.append(key)
        if not fresh: return
        self.status.set(f'正在读取 {len(fresh)} 张图像，识别原标尺并核对尺度…')
        def worker():
            for key in fresh:
                try: self.events.put(('analysis', key, analyze(key)))
                except Exception as e: self.events.put(('analysis_error', key, str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait(); kind = event[0]
                if kind == 'analysis':
                    _, key, a = event
                    if key not in self.items: continue
                    self.items[key] = a
                    state = self.scale_state(key)
                    self.tree.item(key, values=(state,), tags=('warn',) if a.requires_confirmation or not a.nm_per_pixel else ())
                    if self.current is None:
                        self.tree.selection_set(key); self.select()
                    self.status.set(f'已读取 {sum(a is not None for a in self.items.values())}/{len(self.items)} 张图像')
                elif kind == 'analysis_error':
                    _, key, error = event
                    if key in self.items:
                        self.tree.item(key, values=('读取失败',), tags=('error',))
                        self.status.set(f'{Path(key).name}：{error}')
                elif kind == 'preview':
                    _, rev, image, report = event
                    if rev != self.revision: continue
                    self.preview_image = image
                    self.preview_report = report
                    self.draw_preview()
                    self.status.set('预览已更新；' + (report.get('warnings') or '可导出'))
                elif kind == 'preview_error':
                    _, rev, error = event
                    if rev == self.revision:
                        self.preview_image = None; self.draw_preview()
                        self.status.set(error)
                elif kind == 'export_progress':
                    _, key, path, done, total = event
                    if path: self.last_exports[key] = path
                    self.progress.configure(value=done, maximum=total)
                    self.status.set(f'导出 {done}/{total}：{Path(key).name}')
                elif kind == 'export_done':
                    _, successes, failures, cancelled, report = event
                    self.exporting = False
                    self.status.set(f'导出完成：成功 {successes}，失败 {len(failures)}' + ('（已取消）' if cancelled else '') + f'；记录：{report}')
                    if failures: messagebox.showwarning('部分图像未导出', '\n'.join(failures[:12]) + '\n\n完整列表见批处理 CSV。')
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def select(self, event=None):
        selection = self.tree.selection()
        if not selection: return
        key = selection[0]
        if self.items.get(key) is None: return
        self.current = key
        self.zoom_factor = 1
        a = self.items[key]
        value = self.scales.get(key, a.nm_per_pixel)
        source = '手动校准' if key in self.scales else a.source
        self.scale_var.set(f'{value:.8g}' if value else '')
        recognition = a.recognition.get('status','')
        self.detail.set(f'{Path(key).name}  ·  {a.width} × {a.height} px\n尺度：{value:g} nm/px  ·  {source}\n{recognition}' if value else f'{Path(key).name}  ·  未校准，请输入尺度或画线校准\n{recognition}')
        self.schedule_preview()

    def schedule_preview(self):
        self.revision += 1
        if self.preview_pending:
            self.root.after_cancel(self.preview_pending)
        self.preview_pending = self.root.after(220, self.start_preview)

    def start_preview(self):
        self.preview_pending = None
        if not self.current or not self.items.get(self.current): return
        rev = self.revision
        try: settings = self.get_settings()
        except (ValueError, tk.TclError) as e:
            self.status.set(f'参数有误：{e}'); return
        a = self.items[self.current]
        crop = self.custom_crops.get(self.current)
        scale = self.scales.get(self.current)
        # A missing scale must not hide the image needed for manual calibration.
        if settings.add_bar and (not (scale or a.nm_per_pixel) or (a.requires_confirmation and scale is None)):
            settings.add_bar = False
            a = copy.copy(a)
            a.note += '；预览未画标尺：请先校准或核对自动尺度后导出'
        def worker():
            try:
                image, report = render(a, settings, crop, scale)
                self.events.put(('preview', rev, image, report))
            except Exception as e: self.events.put(('preview_error', rev, str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def draw_preview(self):
        self.canvas.delete('all'); self.photos.clear(); self.transforms.clear()
        if not self.current: return
        original, _ = load_image(self.current)
        result = getattr(self, 'preview_image', None)
        kind = self.preview_kind.get()
        images = [('原始图像', original)] if kind == '原始图像' else [('处理结果', result)]
        if kind == '并排对比': images = [('原始图像', original), ('处理结果', result)]
        cw, ch = max(10, self.canvas.winfo_width()), max(10, self.canvas.winfo_height())
        panel = cw / len(images)
        for i, (label, im) in enumerate(images):
            cx = panel * (i + .5)
            self.canvas.create_text(cx, 18, text=label, fill='#c9d1db', font=('Microsoft YaHei UI', 10))
            if im is None:
                self.canvas.create_text(cx, ch/2, text='参数有误，请查看底部提示', fill='#efb276'); continue
            ratio = min((panel-20)/im.width, (ch-55)/im.height) * self.zoom_factor
            w, h = max(1, round(im.width*ratio)), max(1, round(im.height*ratio))
            thumb = im.resize((w, h), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(thumb); self.photos.append(photo)
            x, y = cx - w/2, (ch+30-h)/2
            self.canvas.create_image(x, y, image=photo, anchor='nw')
            if label == '原始图像':
                self.transforms['original'] = (x, y, w/im.width, h/im.height, im.width, im.height)
                crop = self.custom_crops.get(self.current)
                if crop:
                    x0,y0,x1,y1 = crop
                    self.canvas.create_rectangle(x+x0*w/im.width, y+y0*h/im.height, x+x1*w/im.width, y+y1*h/im.height, outline='#49e0c0', width=2)
        self.canvas.configure(cursor='crosshair' if self.mode.get() != '查看' else '')

    def zoom(self, event):
        self.zoom_factor = max(.5, min(3, self.zoom_factor * (1.1 if event.delta > 0 else 1/1.1)))
        self.draw_preview()

    def change_mode(self):
        if self.mode.get() != '查看': self.preview_kind.set('原始图像')
        self.schedule_preview()

    def image_point(self, x, y):
        transform = self.transforms.get('original')
        if not transform: return None
        ox,oy,sx,sy,w,h = transform
        return max(0,min(w-1,(x-ox)/sx)), max(0,min(h-1,(y-oy)/sy))

    def drag_start(self, event):
        if self.mode.get() == '查看' or not self.image_point(event.x,event.y): return
        self.selection = (event.x, event.y)
        self.canvas.delete('selection')

    def drag_move(self, event):
        if not self.selection: return
        self.canvas.delete('selection')
        shape = self.canvas.create_line if self.mode.get() == '画线校准' else self.canvas.create_rectangle
        shape(*self.selection, event.x, event.y, fill='#55e5c1', width=2, tags='selection') if self.mode.get() == '画线校准' else shape(*self.selection,event.x,event.y,outline='#55e5c1',width=2,tags='selection')

    def drag_end(self, event):
        if not self.selection: return
        p = self.image_point(*self.selection); q = self.image_point(event.x,event.y)
        self.selection = None
        if not p or not q: return
        try:
            if self.mode.get() == '框选裁剪':
                x0,x1 = sorted((round(p[0]),round(q[0]))); y0,y1 = sorted((round(p[1]),round(q[1])))
                if x1-x0 < 32 or y1-y0 < 32: raise ValueError('裁剪区域至少 32 × 32 像素')
                self.custom_crops[self.current] = (x0,y0,x1,y1)
                self.status.set('已设置当前图像裁剪区域')
            else:
                length = float(self.cal_length.get())
                pixels = math.dist(p,q)
                if not math.isfinite(length) or length <= 0 or pixels < 5: raise ValueError('请输入正的标尺长度，并画出至少 5 像素的线')
                factor = {'nm':1,'µm':1000,'mm':1e6}[self.cal_unit.get()]
                self.scale_var.set(f'{length*factor/pixels:.10g}')
                self.apply_scale()
            self.schedule_preview()
        except ValueError as e: messagebox.showerror('操作未应用', str(e))

    def apply_scale(self):
        if not self.current: return
        try:
            scale = float(self.scale_var.get())
            if not math.isfinite(scale) or scale <= 0: raise ValueError('像素尺寸必须是正数')
            self.scales[self.current] = scale
            self.tree.item(self.current, values=('手动校准',), tags=())
            self.detail.set(f'{Path(self.current).name} · 手动尺度：{scale:.8g} nm/像素')
            self.schedule_preview()
        except ValueError as e: messagebox.showerror('无效尺度', str(e))

    def reset_scale(self):
        if self.current:
            self.scales.pop(self.current, None)
            a = self.items[self.current]
            self.tree.item(self.current, values=(self.scale_state(self.current),),tags=('warn',) if a.requires_confirmation or not a.nm_per_pixel else ())
            self.select()

    def scale_state(self, key):
        if key in self.scales: return '手动校准'
        a = self.items[key]
        if not a or not a.nm_per_pixel: return '待校准'
        if a.requires_confirmation: return '需核对'
        return '元数据' if a.source.startswith(('Zeiss','FEI')) else '自动识别'

    def show_recognition(self):
        if not self.current or not self.items.get(self.current): return
        a = self.items[self.current]
        evidence = a.recognition
        dialog = tk.Toplevel(self.root)
        dialog.title('自动识别依据 · '+Path(self.current).name)
        dialog.geometry('780x490')
        dialog.transient(self.root)
        outer = ttk.Frame(dialog,padding=14);outer.pack(fill='both',expand=True)
        image,_ = load_image(self.current)
        line = evidence.get('bar_line')
        box = evidence.get('label_box')
        if line:
            length,x,y=line
            left=max(0,min(x,box[0] if box else x)-20)
            right=min(a.width,max(x+length,box[2] if box else x+length)+20)
            top=max(0,min(y,box[1] if box else y)-20)
            bottom=min(a.height,max(y,box[3] if box else y)+25)
        else:
            left,right=0,a.width
            top=max(0,a.crop_bottom-12) if a.crop_bottom<a.height else int(a.height*.75)
            bottom=a.height
        roi = image.crop((left,top,right,bottom)).convert('RGB')
        draw = ImageDraw.Draw(roi)
        if box:
            x0,y0,x1,y1=box
            draw.rectangle((x0-left-2,y0-top-2,x1-left+2,y1-top+2),outline='#10d9b3',width=2)
        if line:
            length,x,y=line
            draw.line((x-left,y-top,x+length-left,y-top),fill='#ffad42',width=2)
        roi = ImageOps.contain(roi,(744,180),Image.Resampling.NEAREST)
        photo = ImageTk.PhotoImage(roi)
        label = ttk.Label(outer,image=photo);label.image=photo;label.pack(anchor='w',pady=(0,12))
        lines=[f"结果：{evidence.get('status','尚无识别记录')}",f'当前自动尺度：{a.nm_per_pixel:g} nm/像素' if a.nm_per_pixel else '当前自动尺度：未知']
        if evidence.get('text'):
            lines.append(f"原标尺文字：{evidence['text']}")
        if line:
            lines.append(f'橙线：原标尺端点距离 {line[0]} 像素；绿框：识别的文字区域')
        if evidence.get('score') is not None:
            lines.append(f"最低字符形状分数：{evidence['score']:.3f}；与次选字符的最小差值：{evidence.get('margin',0):.3f}")
            lines.append('形状分数用于筛选匹配，不代表识别准确率。')
        if evidence.get('optical_nm_per_pixel'):
            lines.append(f"仅由原标尺算出的尺度：{evidence['optical_nm_per_pixel']:.6g} nm/像素")
        if evidence.get('relative_difference') is not None:
            lines.append(f"与元数据差异：{100*evidence['relative_difference']:.2f}%；本图允许的像素测量容差：{100*evidence['comparison_tolerance']:.2f}%")
        if evidence.get('system_ocr_texts'):
            lines.append('系统 OCR：'+' / '.join(repr(t) for t in evidence['system_ocr_texts']))
        ttk.Label(outer,text='\n'.join(lines),wraplength=740,justify='left').pack(anchor='w')
        ttk.Button(outer,text='关闭',command=dialog.destroy).pack(side='bottom',anchor='e',pady=8)

    def reset_crop(self):
        self.custom_crops.pop(self.current, None); self.schedule_preview()

    def reset_tone(self):
        defaults = Settings()
        for key in ('tone','low','high','black','white','brightness','contrast','gamma','auto_crop'):
            self.vars[key].set(getattr(defaults,key))
        self.schedule_preview()

    def remove(self):
        self.revision += 1
        for key in self.tree.selection():
            self.tree.delete(key); self.items.pop(key,None); self.scales.pop(key,None); self.custom_crops.pop(key,None)
            if self.current == key: self.current = None
        if not self.current:
            self.preview_image = None
            self.canvas.delete('all'); self.detail.set('尚未选择图像')
            children = self.tree.get_children()
            if children: self.tree.selection_set(children[0]); self.select()

    def choose_output(self):
        folder = filedialog.askdirectory()
        if folder: self.output.set(folder)

    def open_output(self):
        path = Path(self.output.get()).resolve(); path.mkdir(parents=True,exist_ok=True)
        if os.name == 'nt': os.startfile(path)

    def export(self, batch):
        if self.exporting:
            messagebox.showinfo('正在导出', '请等待当前批次完成。'); return
        keys = list(self.items) if batch else ([self.current] if self.current else [])
        if not keys: return
        if any(self.items[k] is None and self.tree.item(k,'values')[0] == '读取中' for k in keys):
            messagebox.showinfo('正在识别', '请等待所选图像识别完成。'); return
        try:
            settings = self.get_settings()
            folder = Path(self.output.get()).resolve(); folder.mkdir(parents=True,exist_ok=True)
        except Exception as e:
            messagebox.showerror('无法导出', str(e)); return
        # Snapshot the entire job so edits during export cannot alter its parameters.
        jobs = [(k,copy.copy(self.items[k]),self.custom_crops.get(k),self.scales.get(k)) for k in keys]
        self.cancel.clear(); self.exporting = True
        self.progress.configure(maximum=len(jobs), value=0)
        def worker():
            rows=[]; failures=[]; successes=0
            for i,(key,a,crop,scale) in enumerate(jobs):
                if self.cancel.is_set(): break
                try:
                    if a is None: raise ValueError('图像读取失败')
                    path,report = export_image(a,settings,folder,crop,scale)
                    successes+=1
                    rows.append({'input':key,'output':str(path),'status':'成功','message':report['warnings']})
                    self.events.put(('export_progress',key,str(path),i+1,len(jobs)))
                except Exception as e:
                    failures.append(f'{Path(key).name}：{e}')
                    rows.append({'input':key,'output':'','status':'失败','message':str(e)})
                    self.events.put(('export_progress',key,None,i+1,len(jobs)))
            from datetime import datetime
            log = folder / ('batch_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '.csv')
            try:
                with log.open('w', newline='', encoding='utf-8-sig') as f:
                    writer=csv.DictWriter(f,fieldnames=['input','output','status','message']);writer.writeheader();writer.writerows(rows)
            except OSError as e: failures.append(f'批处理记录保存失败：{e}')
            self.events.put(('export_done',successes,failures,self.cancel.is_set(),str(log)))
        threading.Thread(target=worker,daemon=True).start()

    def copy_current_image(self):
        if not self.current or not self.items.get(self.current):
            self.status.set('请先选择一张已读取的图像。')
            return
        try:
            from .clipboard import copy_image
            settings = self.get_settings()
            image, _ = render(self.items[self.current], settings,
                              self.custom_crops.get(self.current), self.scales.get(self.current))
            copy_image(image, self.root.winfo_id())
            self.status.set(f'已复制当前处理图片（{image.width} × {image.height} px），可直接粘贴。')
        except Exception as e:
            self.status.set(f'复制失败：{e}')
            messagebox.showerror('无法复制图片', str(e))

    def drag_export(self, event):
        if not self.current: return ('none', DND_FILES, '')
        try:
            settings = self.get_settings()
            # Render on drag so the dragged image always reflects current controls.
            image, report = render(self.items[self.current],settings,self.custom_crops.get(self.current),self.scales.get(self.current))
            path = Path(self.drag_temp.name) / (Path(self.current).stem + '_SEM.png')
            image.save(path)
            return (COPY, DND_FILES, (str(path),))
        except Exception as e:
            self.status.set(str(e)); return ('none', DND_FILES, '')

    def save_preset(self):
        try: values = asdict(self.get_settings())
        except Exception as e: messagebox.showerror('参数有误', str(e)); return
        path = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('预设','*.json')])
        if path: Path(path).write_text(json.dumps(values,ensure_ascii=False,indent=2),encoding='utf-8')

    def load_preset(self):
        path = filedialog.askopenfilename(filetypes=[('预设','*.json')])
        if not path: return
        before = {key:v.get() for key,v in self.vars.items()}
        try:
            values = json.loads(Path(path).read_text(encoding='utf-8'))
            for key,value in values.items():
                if key in self.vars: self.vars[key].set(value)
            self.get_settings(); self.schedule_preview()
        except Exception as e:
            for key,value in before.items(): self.vars[key].set(value)
            messagebox.showerror('预设读取失败',str(e))

    def close(self):
        if self.exporting:
            messagebox.showinfo('正在导出','请等待导出结束，或先取消批处理。'); return
        self.cancel.set()
        self.drag_temp.cleanup()
        self.root.destroy()


def main():
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = App(root)
    import sys
    if len(sys.argv) > 1: app.add_paths(sys.argv[1:])
    root.mainloop()
