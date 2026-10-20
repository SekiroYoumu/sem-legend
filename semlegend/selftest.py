"""Release smoke check, also executed inside the packaged Windows program."""
import json
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image
from tkinter import ttk

from . import __version__
from .core import Settings, analyze, render
from .paths import ROOT, RESOURCE_ROOT


def check_tone_controls(root, app):
    """Exercise real Scale/Spinbox callbacks through the asynchronous preview."""
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    def wait_preview(key, value):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            root.update()
            report = getattr(app, 'preview_report', {})
            if report.get('settings', {}).get(key) == value:
                return np.asarray(app.preview_image).copy()
            time.sleep(.02)
        raise AssertionError(f'{key} preview did not update: {app.status.get()}')

    with tempfile.TemporaryDirectory(prefix='semlegend-tone-check-') as temp:
        path = Path(temp) / 'ramp.png'
        Image.fromarray(np.tile(np.arange(32, 224, dtype='uint8'), (64, 1))).save(path)
        key = str(path)
        app.items[key] = analyze(path, use_ocr=False)
        app.current = key
        app.vars['tone'].set('保留原始')
        app.vars['add_bar'].set(False)
        app.schedule_preview()
        wait_preview('brightness', 0)
        results = []
        for name, slider_value, typed_value in [('brightness', 12.5, -8.25),
                                                ('contrast', 1.35, .85),
                                                ('gamma', .75, 1.25)]:
            before = np.asarray(app.preview_image).copy()
            controls = list(descendants(root))
            slider = next(w for w in controls if isinstance(w, ttk.Scale)
                          and str(w.cget('variable')) == str(app.vars[name]))
            slider.set(slider_value)
            changed = wait_preview(name, slider_value)
            assert not np.array_equal(before, changed), name
            entry = next(w for w in controls if isinstance(w, ttk.Spinbox)
                         and str(w.cget('textvariable')) == str(app.vars[name]))
            entry.delete(0, 'end')
            entry.insert(0, str(typed_value))
            entry.event_generate('<FocusOut>')
            changed_again = wait_preview(name, typed_value)
            assert not np.array_equal(changed, changed_again), name
            results.append(name)
        app.current = None
        app.items.pop(key)
        app.reset_tone()
        app.vars['add_bar'].set(True)
        return results


def run(report_path):
    from tkinterdnd2 import TkinterDnD
    from .gui import App

    root = TkinterDnD.Tk()
    root.withdraw()
    app = App(root)
    rows = []
    try:
        root.update()
        dnd_version = str(root.tk.call('package', 'require', 'tkdnd'))
        assert (RESOURCE_ROOT / 'windows_ocr.ps1').is_file()
        tone_controls = check_tone_controls(root, app)
        expected = {'cu_catalyst.jpg': 5000, 'fei_nova_nanocigarette.png': 500,
                    'jeol_neoscope_shell.jpg': 20000, 'silver_nanowires.jpg': 1000}
        for name, value in expected.items():
            path = next((ROOT / 'example').rglob(name))
            a = analyze(path, prefer_metadata=False)
            assert a.recognition['value_nm'] == value, name
            if name == 'jeol_neoscope_shell.jpg':
                assert a.crop_bottom == 1024
            # Smoke-test rendering with an explicit known fixture calibration.
            image, report = render(a, Settings(), manual_scale=value / a.bar_pixels)
            rows.append({'file': name, 'size': image.size, 'bar_pixels': report['bar_pixels'],
                         'requires_confirmation': a.requires_confirmation})
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({'version': __version__, 'tkdnd': dnd_version,
                                          'tone_controls': tone_controls,
                                          'samples': rows, 'passed': True}, indent=2), encoding='utf-8')
    finally:
        app.close()
