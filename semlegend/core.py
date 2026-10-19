from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .recognition import ocr_variants, parse_label, read_label
from .detection import bracket_candidates, grid_footer, solid_candidates, split_candidates
from .paths import ROOT, RESOURCE_ROOT

EXTENSIONS = {'.tif', '.tiff', '.png', '.jpg', '.jpeg', '.bmp'}


@dataclass
class Analysis:
    path: str
    width: int
    height: int
    crop_bottom: int
    nm_per_pixel: float | None = None
    source: str = '未校准'
    note: str = ''
    bar_pixels: int | None = None
    requires_confirmation: bool = False
    recognition: dict = field(default_factory=dict)


@dataclass
class Settings:
    auto_crop: bool = True
    tone: str = '逐图自动'
    low: float = 0.5
    high: float = 99.5
    black: float = 0
    white: float = 255
    brightness: float = 0
    contrast: float = 1
    gamma: float = 1
    add_bar: bool = True
    bar_nm: float = 0
    auto_bar_min_ratio: float = 0.12
    corner: str = '左下'
    color: str = '白色'
    font_ratio: float = 0.0675
    thickness_ratio: float = 0.018
    margin_ratio: float = 0.065
    outline: bool = False
    output_format: str = 'PNG'
    output_width: int = 0


def load_image(path):
    with Image.open(path) as im:
        # Convert palette images using the actual palette; never reinterpret indices.
        im = ImageOps.exif_transpose(im)
        if im.mode in ('I;16', 'I;16L', 'I;16B', 'I', 'F'):
            a = np.asarray(im, dtype=np.float64)
            if not np.isfinite(a).all():
                raise ValueError('图像包含无效像素值')
            lo, hi = float(a.min()), float(a.max())
            a = (a - lo) * 255 / (hi - lo) if hi > lo else np.zeros_like(a)
            return Image.fromarray(np.clip(a, 0, 255).astype('uint8')), '高位深图像已映射到 8 位显示范围'
        if im.mode in ('RGBA', 'LA'):
            rgba = im.convert('RGBA')
            bg = Image.new('RGBA', rgba.size, 'white')
            return Image.alpha_composite(bg, rgba).convert('RGB'), ''
        return im.convert('RGB'), ''


def detect_footer(image):
    """Conservative detection of a wide, dark, text-bearing bottom databar."""
    a = np.asarray(image.convert('L'))
    h, w = a.shape
    dark = (a < 24).mean(axis=1)
    for y in range(int(h * .65), int(h * .97)):
        stop = min(h - 1, y + max(16, int(h * .05)))
        if stop - y < 12:
            continue
        band = a[y:stop]
        # Require both an abrupt boundary and predominantly dark rows below it.
        if dark[y] > .88 and dark[max(0, y - 1)] < .65:
            if np.mean(dark[y:stop] > .65) > .85 and (band > 180).mean() > .004:
                return y
            # Text-rich footers can have half-white rows through the caption/bar.
            # Require a full-width black leading margin and a dark band extending
            # to the bottom, so a dark patch within the specimen is insufficient.
            tail = a[y:]
            if (np.all(dark[y:y + 8] > .95)
                    and dark[y:].mean() > .75
                    and np.all(dark[y:] > .4)
                    and np.all(dark[-5:] > .9)
                    and (tail > 180).mean() > .004):
                return y
    return grid_footer(image)


def metadata_scale(path):
    with Image.open(path) as im:
        tags = getattr(im, 'tag_v2', {})
        text = '\n'.join(str(tags.get(k, '')).replace('\x00', '') for k in (34118, 34119, 270, 34680, 34682))
        # Image Pixel Size is the stored-image calibration, unlike nominal Pixel Size.
        for key in ('Image Pixel Size', 'Pixel Size'):
            m = re.search(r'(?im)^\s*' + key + r'\s*=\s*([\d.eE+\-]+)\s*(nm|[µμu]m|pm|mm|m)\b', text)
            if m:
                value = float(m[1]) * unit_nm(m[2])
                if math.isfinite(value) and value > 0:
                    return value, 'Zeiss ' + key
        # FEI TIFF metadata uses metres per pixel.
        m = re.search(r'(?im)^\s*PixelWidth\s*=\s*([\d.eE+\-]+)', text)
        if m:
            value = float(m[1]) * 1e9
            if math.isfinite(value) and value > 0:
                return value, 'FEI PixelWidth'
    return None, '未校准'


def unit_nm(unit):
    return {'nm': 1, 'um': 1000, 'µm': 1000, 'μm': 1000, 'mm': 1e6, 'm': 1e9, 'pm': .001}[unit]


def find_bar(image, footer):
    if footer >= image.height:
        return None
    a = np.asarray(image.convert('L'))
    # Only inspect the left scale compartment, excluding magnification text.
    region = a[footer + 2:image.height - 2, :int(image.width * .28)]
    candidates = []
    for yy, row in enumerate(region > 180):
        edges = np.diff(np.r_[False, row, False].astype('int8'))
        for x0, x1 in zip(np.where(edges == 1)[0], np.where(edges == -1)[0]):
            length = int(x1 - x0 - 1)  # distance between terminal pixel centres
            if 15 <= length <= image.width * .25:
                y = footer + 2 + yy
                # A horizontal scale line is far longer than adjacent glyph strokes.
                if yy > 8:
                    candidates.append((length, int(x0), y))
    selected = max(candidates, default=None)
    if selected:
        length, x, y = selected
        # For bracket bars, measure tick centres rather than their outside edges.
        probe = a[max(footer,y-9):max(footer,y-3), x:x+length+1] > 180
        if probe.shape[0] >= 3:
            columns = probe.mean(axis=0) > .7
            edges = np.diff(np.r_[False,columns,False].astype('int8'))
            runs = list(zip(np.where(edges==1)[0], np.where(edges==-1)[0]))
            if len(runs)==2 and runs[0][0] <= 2 and runs[-1][1] >= length-1:
                centres = [(lo+hi-1)/2 for lo,hi in runs]
                length = round(centres[1]-centres[0])
        return length,x,y
    return None


def ocr_text(image):
    with tempfile.TemporaryDirectory(prefix='semlegend-') as temp:
        path = Path(temp) / 'label.png'
        image.convert('RGB').save(path)
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        if os.name == 'nt':
            try:
                p = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                                    str(RESOURCE_ROOT / 'windows_ocr.ps1'), str(path)], capture_output=True,
                                   timeout=25, creationflags=flags)
                if p.returncode == 0:
                    text = json.loads(p.stdout.decode('utf-8-sig'))['text']
                    if text.strip():
                        return text
            except (OSError, subprocess.TimeoutExpired, ValueError, KeyError):
                pass
        exe = shutil.which('tesseract')
        if exe:
            p = subprocess.run([exe, str(path), 'stdout', '--psm', '7'], capture_output=True,
                               timeout=20, creationflags=flags)
            if p.returncode == 0:
                return p.stdout.decode('utf-8', errors='replace')
    return ''


def analyze(path, use_ocr=True, prefer_metadata=True):
    path = Path(path).resolve()
    image, note = load_image(path)
    footer = detect_footer(image)
    scale, source = metadata_scale(path)
    if not prefer_metadata:
        scale, source = None, '未校准'
    bar = find_bar(image, footer)
    layouts=[]
    if use_ocr:
        if bar:
            layouts.append({'bar':bar,'layout':'端点刻线 + 上方文字','label_box':None,'dark_text':False})
        layouts.extend(split_candidates(image))
        # Test additional geometry when the original left-hand layout is absent.
        layouts.extend(bracket_candidates(image))
        layouts.extend(solid_candidates(image,footer))
    result = Analysis(str(path), image.width, image.height, footer, scale, source, note,
                      bar[0] if bar else None)
    result.recognition = {'footer_y':footer,'bar_line':bar,'metadata_scale':scale,
                          'metadata_source':source if scale else None}
    if use_ocr and layouts:
        choices=[]
        for candidate in layouts[:30]:
            candidate_bar=candidate['bar']
            optical=read_label(image,footer,candidate_bar,candidate.get('label_box'),candidate.get('dark_text',False))
            optical.update(layout=candidate['layout'],dark_text=candidate.get('dark_text',False))
            choices.append((candidate,optical))
            if optical.get('automatic'):
                break
        # Prefer syntactically valid scale labels over unrelated high-score text.
        chosen,optical=max(choices,key=lambda c:(bool(c[1].get('automatic')),c[1].get('value_nm') is not None,c[1].get('score',0)))
        bar=chosen['bar'];result.bar_pixels=bar[0]
        result.recognition['bar_line']=bar
        result.recognition.update(optical)
        if optical.get('automatic'):
            optical_scale = optical['value_nm']/bar[0]
            result.recognition['optical_nm_per_pixel'] = optical_scale
            if scale is not None:
                difference = abs(optical_scale-scale)/scale
                tolerance = max(.03,1.5/bar[0])
                result.recognition.update(relative_difference=difference, comparison_tolerance=tolerance)
                if difference > tolerance:
                    result.requires_confirmation = True
                    result.recognition['status'] = '元数据与原标尺不一致，需核对'
                    result.note = (note+'；' if note else '') + f'尺度冲突：元数据 {scale:g} nm/px，原标尺 {optical_scale:.5g} nm/px'
                else:
                    result.recognition['status'] = '元数据与原标尺交叉核对通过'
            else:
                result.nm_per_pixel = optical_scale
                result.source = '原标尺形状识别'
                result.note = f"识别 {optical['text']}；端点距离 {bar[0]} px；形状分数 {optical['score']:.3f}（非准确率）"
                if note:
                    result.note = note+'；'+result.note
        elif scale is None and optical.get('value_nm') is not None and optical.get('score',0)>=.84 and optical.get('margin',0)>=.005:
            result.nm_per_pixel=optical['value_nm']/bar[0]
            result.source='形状识别（需核对）'
            result.requires_confirmation=True
            result.recognition['status']='已找到标尺，字符存在歧义，需核对'
            result.recognition['optical_nm_per_pixel']=result.nm_per_pixel
            result.note=(note+'；' if note else '')+f"建议文字 {optical['text']}；请核对后应用尺度"
        elif scale is None:
            texts=[]
            if optical.get('label_box'):
                for variant in ocr_variants(image,optical['label_box'],optical.get('dark_text',False)):
                    texts.append(ocr_text(variant))
            result.recognition['system_ocr_texts'] = texts
            candidates=[(text,parse_label(text)) for text in texts]
            candidates=[(text,nm) for text,nm in candidates if nm is not None]
            if optical.get('value_nm') is not None and any(nm!=optical['value_nm'] for _,nm in candidates):
                candidates=[]
                result.recognition['status']='文字形状与系统 OCR 数值或单位冲突，需手动核对'
            if candidates and all(nm==candidates[0][1] for _,nm in candidates):
                text,nm=candidates[0]
                result.nm_per_pixel=nm/bar[0]
                result.source='OCR 原标尺（需核对）'
                result.requires_confirmation=True
                result.recognition['status']='系统 OCR 建议值，需核对'
                result.note=(note+'；' if note else '')+'系统 OCR：'+text
            else:
                result.note=(note+'；' if note else '')+'自动识别未成功或结果有歧义，请手动校准'
    elif scale is None:
        result.recognition['status']='找不到可识别的原标尺' if use_ocr else '文字识别未启用'
    if scale is not None and not result.recognition.get('status'):
        result.recognition['status']='元数据尺度（未做光学交叉核对）'
    return result


def crop_box(image, analysis, settings, custom=None):
    box = custom or (0, 0, image.width, analysis.crop_bottom if settings.auto_crop else image.height)
    x0, y0, x1, y1 = map(int, box)
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
        raise ValueError('裁剪范围超出图像或为空')
    if x1 - x0 < 32 or y1 - y0 < 32:
        raise ValueError('裁剪区域至少需要 32 × 32 像素')
    return x0, y0, x1, y1


def nice_length(target, round_up=False):
    power = 10 ** math.floor(math.log10(target))
    if round_up:
        return min(x*power for x in (1,2,5,10) if x*power >= target)
    return max(x * power / 10 for x in (1, 2, 5, 10, 20, 50) if x * power / 10 <= target)


def format_length(nm):
    if nm >= 1e6:
        return f'{nm / 1e6:g} mm'
    if nm >= 1000:
        return f'{nm / 1000:g} µm'
    return f'{nm:g} nm'


def font(size):
    for name in ('C:/Windows/Fonts/arialbd.ttf', 'DejaVuSans-Bold.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(name, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def render(analysis, settings, custom=None, manual_scale=None):
    image, _ = load_image(analysis.path)
    box = crop_box(image, analysis, settings, custom)
    image = image.crop(box).convert('L')
    a = np.asarray(image, dtype=np.float32)
    if settings.tone == '逐图自动':
        if not 0 <= settings.low < settings.high <= 100:
            raise ValueError('百分位范围需要满足 0 ≤ 黑场 < 白场 ≤ 100')
        lo, hi = np.percentile(a, [settings.low, settings.high])
    elif settings.tone == '固定黑白场':
        lo, hi = settings.black, settings.white
        if hi <= lo:
            raise ValueError('白场必须大于黑场')
    else:
        lo, hi = 0, 255
    if hi > lo:
        a = (a - lo) * (255 / (hi - lo))
    if settings.gamma <= 0 or settings.contrast <= 0:
        raise ValueError('Gamma 和对比度必须大于 0')
    a = np.clip((a - 127.5) * settings.contrast + 127.5 + settings.brightness, 0, 255)
    a = 255 * (a / 255) ** (1 / settings.gamma)
    image = Image.fromarray(np.round(a).astype('uint8')).convert('RGB')
    scale = manual_scale if manual_scale is not None else analysis.nm_per_pixel
    if scale is not None and (not math.isfinite(scale) or scale <= 0):
        raise ValueError('像素尺寸必须为正数')
    if settings.output_width:
        if not 64 <= settings.output_width <= 16384:
            raise ValueError('输出宽度应为 64–16384，或 0 保持原尺寸')
        width = settings.output_width
        if scale:
            scale *= image.width / width
        image = image.resize((width, max(1, round(image.height * width / image.width))), Image.Resampling.LANCZOS)
    report = {'input': analysis.path, 'crop': box, 'nm_per_pixel_input': manual_scale or analysis.nm_per_pixel,
              'nm_per_pixel_output': scale, 'calibration_source': '手动输入' if manual_scale is not None else analysis.source,
              'tone_black': float(lo), 'tone_white': float(hi), 'settings': asdict(settings),
              'warnings': analysis.note, 'output_size': image.size,
              'recognition': analysis.recognition}
    if settings.add_bar:
        if not scale:
            raise ValueError('没有可靠尺度，无法添加标尺。请先校准，或关闭添加标尺。')
        if analysis.requires_confirmation and manual_scale is None:
            raise ValueError('自动尺度需要核对：请检查像素尺寸后点击「应用到当前图像」。')
        if not .01 <= settings.auto_bar_min_ratio <= .5:
            raise ValueError('自动标尺最小长度比例应在 0.01–0.5 之间')
        nm = settings.bar_nm or nice_length(image.width * scale * settings.auto_bar_min_ratio, round_up=True)
        pixels = round(nm / scale)
        if pixels < 3 or pixels > image.width * .8:
            raise ValueError('标尺太长或太短，请修改标尺长度或裁剪范围')
        draw = ImageDraw.Draw(image)
        margin = max(6, round(min(image.size) * settings.margin_ratio))
        thick = max(2, round(image.height * settings.thickness_ratio))
        f = font(max(10, round(image.height * settings.font_ratio)))
        label = format_length(nm)
        bounds = draw.textbbox((0, 0), label, font=f)
        tw, th = bounds[2] - bounds[0], bounds[3] - bounds[1]
        group_w = max(pixels, tw)
        gap = max(4, thick)
        group_h = th + gap + thick
        if group_w + 2 * margin > image.width or group_h + 2 * margin > image.height:
            raise ValueError('标尺文字放不下，请缩小字体或边距')
        gx = margin if '左' in settings.corner else image.width - margin - group_w
        gy = image.height - margin - group_h if '下' in settings.corner else margin
        bx = gx + (group_w - pixels) // 2
        by = gy + th + gap
        fill = 'white' if settings.color == '白色' else 'black'
        stroke = 'black' if fill == 'white' else 'white'
        sw = max(1, round(image.height / 500)) if settings.outline else 0
        if sw:
            draw.rectangle((bx-sw, by-sw, bx+pixels-1+sw, by+thick-1+sw), fill=stroke)
        draw.rectangle((bx, by, bx + pixels - 1, by + thick - 1), fill=fill)
        draw.text((gx + (group_w-tw)//2 - bounds[0], gy-bounds[1]), label, font=f, fill=fill,
                  stroke_width=sw, stroke_fill=stroke)
        report.update(bar_nm=nm, bar_pixels=pixels, bar_label=label,
                      bar_rounding_error_percent=100 * (pixels * scale / nm - 1))
    return image, report


def unique_path(folder, stem, suffix):
    path = Path(folder) / (stem + suffix)
    counter = 2
    while path.exists() or path.with_suffix('.json').exists():
        path = Path(folder) / f'{stem}_{counter}{suffix}'
        counter += 1
    return path


def export_image(analysis, settings, folder, custom=None, manual_scale=None):
    image, report = render(analysis, settings, custom, manual_scale)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = '.tif' if settings.output_format == 'TIFF' else '.png'
    path = unique_path(folder, Path(analysis.path).stem + '_SEM', suffix)
    kwargs = {'compression': 'tiff_lzw'} if suffix == '.tif' else {}
    if suffix == '.tif' and report['nm_per_pixel_output']:
        # Pixels per centimetre, understood by ImageJ/Fiji.
        kwargs.update(dpi=(2.54e7 / report['nm_per_pixel_output'],) * 2)
    image.convert('L').save(path, **kwargs)
    report['output'] = str(path)
    path.with_suffix('.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return path, report
