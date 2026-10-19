from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from semlegend.core import Settings, analyze, export_image, find_bar, render
from semlegend.recognition import glyph_templates, parse_label, read_label
from tests.sample_data import sample_path

ROOT=Path(__file__).resolve().parents[1]
FONT=Path('C:/Windows/Fonts/ariali.ttf')
pytestmark=pytest.mark.skipif(not glyph_templates(),reason='No supported system fonts are installed')


def test_all_examples_optically_without_metadata(monkeypatch):
    # Force the visual route for every image, including the ten metadata-rich
    # originals. No template is trained or extracted from any of these files.
    def unexpected_native_ocr(image):
        raise AssertionError('High-match samples should not need system OCR')
    monkeypatch.setattr('semlegend.core.ocr_text',unexpected_native_ocr)
    expected={'200rpm1.tif':20000,'200rpm2.tif':20000,'200rpm21.tif':2000,
              '200rpm22.tif':10000,'200rpm3.tif':2000,'200rpm31.tif':10000,
              '200rpm31(1).tif':10000,'O03.tif':10000,'O05.tif':20000,
              'QT02.tif':10000,'QT03.tif':10000}
    for name,nm in expected.items():
        a=analyze(sample_path(name),prefer_metadata=False)
        assert a.source=='原标尺形状识别'
        assert not a.requires_confirmation
        assert a.recognition['value_nm']==nm
        assert a.nm_per_pixel == nm/a.bar_pixels
        _,report=render(a,Settings())
        assert report['recognition']['automatic'] is True


def test_metadata_optical_agreement_and_serializable_export(tmp_path):
    a=analyze(sample_path('200rpm22.tif'))
    assert a.recognition['relative_difference']<.01
    assert a.source=='Zeiss Image Pixel Size'
    assert not a.requires_confirmation
    output,_=export_image(a,Settings(),tmp_path)
    assert output.with_suffix('.json').is_file()


@pytest.mark.skipif(not FONT.exists(),reason='Synthetic font fixture needs Arial Italic')
@pytest.mark.parametrize('label,nm',[('500 nm',500),('3.2 nm',3.2),('2.5 µm',2500),('125 µm',125000),('0.5 mm',500000)])
def test_unseen_numeric_values_and_units(label,nm):
    image=synthetic(label)
    result=read_label(image,691,find_bar(image,691))
    assert result['automatic'] is True
    assert result['value_nm']==pytest.approx(nm)


def synthetic(label):
    image=Image.new('L',(1024,768),80)
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,691,1024,768),fill=0)
    draw.text((24,692),label,font=ImageFont.truetype(str(FONT),24),fill=255)
    draw.line((19,734,145,734),fill=255,width=2)
    draw.line((19,724,19,744),fill=255,width=2)
    draw.line((145,724,145,744),fill=255,width=2)
    return image


@pytest.mark.skipif(not FONT.exists(),reason='Synthetic font fixture needs Arial Italic')
def test_non_scale_text_rejected():
    for text in ['nonsense','Mag=700X','10','um']:
        image=synthetic(text)
        assert not read_label(image,691,find_bar(image,691))['automatic']


@pytest.mark.skipif(not FONT.exists(),reason='Synthetic font fixture needs Arial Italic')
def test_metadata_conflict_does_not_silently_export(tmp_path):
    path=tmp_path/'conflict.tif'
    synthetic('10 µm').save(path,tiffinfo={34118:'Image Pixel Size = 500 nm\n'})
    a=analyze(path)
    assert a.nm_per_pixel==500
    assert a.requires_confirmation
    assert a.recognition['relative_difference']>.8
    with pytest.raises(ValueError,match='需要核对'):
        render(a,Settings())


def test_no_guessing_unit_or_missing_value():
    assert parse_label('10') is None
    assert parse_label('µm') is None
    assert parse_label('40 pm') == .04
    assert parse_label('10 μm') == 10000
    assert parse_label('2,5 um') == 2500


def test_resized_antialiased_small_text_remains_readable():
    with Image.open(sample_path('200rpm22.tif')) as raw:
        image=raw.convert('L').resize((1536,1152),Image.Resampling.LANCZOS)
    from semlegend.core import detect_footer
    footer=detect_footer(image)
    result=read_label(image,footer,find_bar(image,footer))
    assert result['automatic']
    assert result['value_nm']==10000
    assert len(result['threshold_checks'])==2
