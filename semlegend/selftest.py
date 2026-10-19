"""Release smoke check, also executed inside the packaged Windows program."""
import json
from pathlib import Path

from . import __version__
from .core import Settings, analyze, render
from .paths import ROOT, RESOURCE_ROOT


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
                                          'samples': rows, 'passed': True}, indent=2), encoding='utf-8')
    finally:
        app.close()
