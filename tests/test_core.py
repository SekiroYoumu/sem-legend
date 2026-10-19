import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from semlegend.core import Settings, analyze, detect_footer, export_image, metadata_scale, render

from tests.sample_data import sample_path


def test_example_metadata_and_crop():
    expected = {'200rpm1.tif':558.3, '200rpm2.tif':159.5, '200rpm21.tif':55.82,
                '200rpm22.tif':159.5, '200rpm3.tif':55.82, '200rpm31.tif':159.5,
                'O03.tif':111.6, 'O05.tif':159.5, 'QT02.tif':159.5, 'QT03.tif':159.5}
    for name, scale in expected.items():
        a = analyze(sample_path(name), use_ocr=False)
        assert a.nm_per_pixel == pytest.approx(scale)
        assert a.crop_bottom == 691
    assert metadata_scale(sample_path('200rpm31(1).tif'))[0] is None


def test_no_footer_on_ordinary_image():
    assert detect_footer(Image.new('RGB', (1024,768), 'black')) == 768
    rng = np.random.default_rng(1)
    assert detect_footer(Image.fromarray(rng.integers(0,256,(768,1024),dtype='uint8'))) == 768


def test_unknown_scale_does_not_produce_false_bar():
    a = analyze(sample_path('200rpm31(1).tif'), use_ocr=False)
    with pytest.raises(ValueError,match='没有可靠尺度'):
        render(a,Settings())
    im,report = render(a,Settings(),manual_scale=159.5)
    assert im.size == (1024,691)
    assert report['calibration_source'] == '手动输入'


def test_resize_preserves_physical_bar_and_export_metadata(tmp_path):
    a=analyze(sample_path('200rpm22.tif'), use_ocr=False)
    settings=Settings(output_width=512,bar_nm=10000,output_format='TIFF')
    path,report=export_image(a,settings,tmp_path)
    assert report['nm_per_pixel_output'] == pytest.approx(319)
    assert report['bar_pixels'] == round(10000/319)
    with Image.open(path) as im:
        assert im.width == 512
        assert im.info['dpi'][0] == pytest.approx(2.54e7/319,rel=1e-6)
    assert json.loads(path.with_suffix('.json').read_text(encoding='utf-8'))['bar_nm']==10000
    second,_=export_image(a,settings,tmp_path)
    assert second != path


def test_tone_preserve_and_crop(tmp_path):
    path=tmp_path/'ramp.png'
    data=np.tile(np.arange(256,dtype='uint8'),(100,1))
    Image.fromarray(data).save(path)
    a=analyze(path,use_ocr=False)
    im,_=render(a,Settings(tone='保留原始',add_bar=False),custom=(20,10,240,90))
    np.testing.assert_array_equal(np.asarray(im)[:,:,0],data[10:90,20:240])
    with pytest.raises(ValueError,match='白场'):
        render(a,Settings(tone='固定黑白场',black=200,white=100,add_bar=False))


def test_bar_pixels_are_drawn_at_reported_width():
    a=analyze(sample_path('200rpm22.tif'), use_ocr=False)
    im,r=render(a,Settings(bar_nm=10000))
    pixels=r['bar_pixels']; margin=round(min(im.size)*.065)
    y=im.height-margin-1
    white=np.all(np.asarray(im)[y] == 255,axis=1)
    edges=np.diff(np.r_[False,white,False].astype('int8'))
    lengths=np.where(edges==-1)[0]-np.where(edges==1)[0]
    assert pixels in lengths


def test_stored_image_calibration_takes_precedence(tmp_path):
    path=tmp_path/'metadata.tif'
    Image.new('L',(100,100),100).save(path,tiffinfo={34118:'Pixel Size = 100 nm\nImage Pixel Size = 50 nm\n'})
    assert metadata_scale(path)[0] == 50


def test_ocr_scale_requires_confirmation():
    a=analyze(sample_path('200rpm22.tif'),use_ocr=False)
    a.source='OCR 原标尺（建议核对）'
    a.requires_confirmation=True
    with pytest.raises(ValueError,match='自动尺度需要核对'):
        render(a,Settings())
    image,_=render(a,Settings(),manual_scale=a.nm_per_pixel)
    assert image.height==691
