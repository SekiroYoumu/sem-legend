"""Regression checks for fractional GUI parameters and integer output width."""
from dataclasses import fields
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from semlegend.core import Settings, analyze, export_image, render
from semlegend.gui import App


class Value:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def gui_settings(**changes):
    defaults = Settings()
    variables = {f.name: Value(changes.get(f.name, getattr(defaults, f.name)))
                 for f in fields(defaults)}
    return App.get_settings(SimpleNamespace(vars=variables))


@pytest.mark.parametrize('key,value', [('brightness', 12.5), ('contrast', 1.35),
                                      ('gamma', .75), ('black', 12.5), ('white', 240.5)])
def test_fractional_tone_values_are_accepted(key, value):
    assert getattr(gui_settings(**{key: str(value)}), key) == value


def test_output_width_still_requires_an_integer():
    assert gui_settings(output_width='512.0').output_width == 512
    with pytest.raises(ValueError, match='输出宽度必须是整数'):
        gui_settings(output_width='512.5')


@pytest.mark.parametrize('changes', [{'brightness': 12.5}, {'contrast': 1.35}, {'gamma': .75}])
def test_gui_tone_settings_change_preview_and_export(tmp_path, changes):
    path = tmp_path / 'ramp.png'
    Image.fromarray(np.tile(np.arange(32, 224, dtype='uint8'), (64, 1))).save(path)
    analysis = analyze(path, use_ocr=False)
    baseline, _ = render(analysis, gui_settings(tone='保留原始', add_bar=False))
    settings = gui_settings(tone='保留原始', add_bar=False, **changes)
    preview, _ = render(analysis, settings)
    assert not np.array_equal(np.asarray(baseline), np.asarray(preview))
    exported, report = export_image(analysis, settings, tmp_path / 'output')
    with Image.open(exported) as image:
        np.testing.assert_array_equal(np.asarray(image.convert('RGB')), np.asarray(preview))
    for key, value in changes.items():
        assert report['settings'][key] == value
