from pathlib import Path

import pytest
from PIL import Image,ImageDraw,ImageFont

from semlegend.core import Settings,analyze,render,nice_length,detect_footer
from tests.sample_data import sample_path

ROOT=Path(__file__).resolve().parents[1]
FONT=Path('C:/Windows/Fonts/arial.ttf')


def test_current_font_and_halved_minimum_auto_length():
    s=Settings()
    assert s.font_ratio == pytest.approx(.045*1.5)
    assert s.auto_bar_min_ratio == pytest.approx(.24/2)
    a=analyze(sample_path('200rpm22.tif'),use_ocr=False)
    im,r=render(a,s)
    assert r['bar_pixels']>=im.width*.12-1
    assert r['bar_nm'] in [x*10**k for x in (1,2,5) for k in range(0,9)]


def test_neoscope_text_rich_footer():
    p=ROOT/'example'/'06_JEOL_NeoScope'/'jeol_neoscope_shell.jpg'
    with Image.open(p) as image:
        assert detect_footer(image)==1024
    a=analyze(p,prefer_metadata=False)
    assert a.crop_bottom==1024
    assert a.recognition['value_nm']==20000
    assert a.requires_confirmation


def test_dark_patch_above_bottom_is_not_footer():
    image=Image.new('L',(500,400),120)
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,330,499,375),fill=0)
    draw.rectangle((60,346,290,357),fill=255)
    assert detect_footer(image)==400


@pytest.mark.parametrize('name,nm',[('4.tif',100000),('5.tif',10000),('6.tif',10000)])
def test_jeol_solid_bar_and_joined_unit(name,nm):
    p=sample_path(name)
    if not p.exists():pytest.skip('Additional user sample is not available')
    a=analyze(p,prefer_metadata=False)
    assert a.nm_per_pixel and not a.requires_confirmation
    assert a.recognition['value_nm']==nm
    assert a.recognition['layout']=='实心横条（白色）'
    assert a.crop_bottom==960


@pytest.mark.skipif(not FONT.exists(),reason='Synthetic fixture needs Arial')
def test_fei_split_bar_with_label_in_gap(tmp_path):
    image=Image.new('L',(1024,768),0)
    draw=ImageDraw.Draw(image)
    draw.text((715,710),'50 µm',font=ImageFont.truetype(str(FONT),22),fill=255)
    draw.line((610,725,705,725),fill=255,width=3)
    draw.line((790,725,885,725),fill=255,width=3)
    for x in [610,885]:draw.line((x,718,x,732),fill=255,width=2)
    p=tmp_path/'split.png';image.save(p)
    a=analyze(p)
    assert a.recognition['value_nm']==50000
    assert a.recognition['layout']=='中间文字分段标尺'


@pytest.mark.parametrize('file,nm,tier',[
    ('cu_catalyst.jpg',5000,'automatic'),
    ('fei_nova_nanocigarette.png',500,'automatic'),
    ('jeol_neoscope_shell.jpg',20000,'review'),
    ('silver_nanowires.jpg',1000,'review'),
    ('tescan_mira_1.jpg',500000,'review'),
    ('tescan_mira_2.jpg',500000,'review'),
    ('tescan_mira_3.jpg',500000,'review'),
])
def test_optional_public_samples(file,nm,tier):
    p=ROOT/'validation_output'/'public_sem'/file
    if not p.exists():p=next((ROOT/'example').rglob(file),p)
    if not p.exists():pytest.skip('Public sample has not been downloaded')
    a=analyze(p,prefer_metadata=False)
    assert a.recognition['value_nm']==nm
    assert a.requires_confirmation == (tier=='review')
    if a.requires_confirmation:
        with pytest.raises(ValueError,match='需要核对'):render(a,Settings())


@pytest.mark.parametrize('name',['FEI-Helios-Ebeam-8bits.tif','FEI-Helios-Ebeam-16bits.tif'])
def test_optional_fei_tiff_and_no_metadata_copy(name,tmp_path):
    p=ROOT/'validation_output'/'fei_samples'/name
    if not p.exists():pytest.skip('Public sample has not been downloaded')
    from semlegend.core import load_image,metadata_scale
    assert metadata_scale(p)[0]==pytest.approx(3372.4)
    image,_=load_image(p)
    clean=tmp_path/'stripped.png';image.save(clean)
    a=analyze(clean)
    assert a.recognition['value_nm']==500000
    assert not a.requires_confirmation
    assert a.crop_bottom==442
    assert abs(a.nm_per_pixel-3372.4)/3372.4<.02


@pytest.mark.parametrize('name',['FEI-Helios-navcam-with-no-IRBeam-bad-floats.tif','FEI-Helios-navcam-with-no-IRBeam.tif','FEI-Helios-navcam.tif'])
def test_scale_less_negative_controls(name):
    p=ROOT/'validation_output'/'fei_samples'/name
    if not p.exists():pytest.skip('Public sample has not been downloaded')
    a=analyze(p,prefer_metadata=False)
    assert a.nm_per_pixel is None


def test_optional_black_bar_on_white_panel():
    p=ROOT/'validation_output'/'fei_samples'/'processed_black_bar.png'
    if not p.exists():pytest.skip('Public sample has not been downloaded')
    a=analyze(p)
    assert a.recognition['value_nm']==50000
    assert a.recognition['layout']=='实心横条（黑色）'
    assert a.requires_confirmation
