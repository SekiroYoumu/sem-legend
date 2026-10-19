"""Small-font scale-label recognition using only Pillow and NumPy.

Templates are rendered from installed system fonts, never copied from input
images or inferred from their filenames, magnification, or metadata.
"""
from __future__ import annotations

import math
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


def runs(values):
    edges = np.diff(np.r_[False, values, False].astype('int8'))
    return [(int(lo),int(hi)) for lo,hi in zip(np.where(edges == 1)[0], np.where(edges == -1)[0])]


def components(mask):
    """8-connected foreground components, sufficient for a tiny label ROI."""
    visited = np.zeros_like(mask, dtype=bool)
    result = []
    height, width = mask.shape
    for y, x in zip(*np.where(mask)):
        if visited[y, x]:
            continue
        stack = [(y, x)]
        visited[y, x] = True
        points = []
        while stack:
            yy, xx = stack.pop()
            points.append((yy, xx))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = yy + dy, xx + dx
                    if 0 <= ny < height and 0 <= nx < width and mask[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
        if len(points) >= 2:
            ys, xs = zip(*points)
            box = (int(min(xs)), int(min(ys)), int(max(xs) + 1), int(max(ys) + 1))
            glyph = np.zeros((box[3]-box[1], box[2]-box[0]), dtype=bool)
            for yy, xx in points:
                glyph[yy-box[1], xx-box[0]] = True
            result.append((box, glyph))
    return sorted(result, key=lambda item: item[0][0])


def label_region(image, footer, bar, threshold=150):
    """Find a separate line of label text above a horizontal scale bar."""
    length, x, y = bar
    left = max(0, x - 25)
    right = min(image.width, int(image.width*.28), max(x + length + 40, int(image.width*.2)))
    bottom = max(footer, y - 3)
    if bottom - footer < 8 or right - left < 15:
        return None
    a = np.asarray(image.convert('L'))[footer:bottom, left:right]
    bright = a > threshold
    bands = runs(bright.any(axis=1))
    if not bands:
        return None
    # Two thin bracket ticks are not a text line. Include descenders such as µ.
    bands = [(lo, hi) for lo, hi in bands if hi-lo >= 5 and bright[lo:hi].sum() >= 20]
    if not bands:
        return None
    lo, hi = max(bands, key=lambda r: int(bright[r[0]:r[1]].sum()))
    mask = bright[lo:hi]
    xs = np.where(mask.any(axis=0))[0]
    if not len(xs):
        return None
    x0, x1 = int(xs[0]), int(xs[-1]+1)
    box = (left+x0, footer+lo, left+x1, footer+hi)
    return box, mask[:,x0:x1]


def normalize(mask):
    ys, xs = np.where(mask)
    if not len(xs):
        return None
    tight = mask[min(ys):max(ys)+1, min(xs):max(xs)+1]
    im = Image.fromarray(tight.astype('uint8')*255)
    return np.asarray(im.resize((32,40), Image.Resampling.BILINEAR),dtype=np.float32)/255


@lru_cache(maxsize=1)
def glyph_templates():
    candidates = [
        'C:/Windows/Fonts/ariali.ttf', 'C:/Windows/Fonts/arial.ttf',
        'C:/Windows/Fonts/arialbi.ttf', 'C:/Windows/Fonts/arialbd.ttf',
        'C:/Windows/Fonts/cour.ttf', 'C:/Windows/Fonts/courbd.ttf',
        'C:/Windows/Fonts/tahoma.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/Supplemental/Arial Italic.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
    ]
    templates = []
    for filename in candidates:
        if not Path(filename).is_file():
            continue
        for size in list(range(7, 33))+[36,40,48,56,64,80,96]:
            font = ImageFont.truetype(filename, size)
            # Include distractor characters so an unrelated word cannot silently
            # become a digit/unit simply because no other class was available.
            for character in '0123456789µunmpoOIlxk':
                im = Image.new('L',(180,160))
                ImageDraw.Draw(im).text((12,0),character,font=font,fill=255)
                mask = np.asarray(im)>120
                vector = normalize(mask)
                if vector is None:
                    continue
                ys,xs = np.where(mask)
                ratio = (max(xs)-min(xs)+1)/(max(ys)-min(ys)+1)
                templates.append((character,vector,float(ratio)))
    return templates


@lru_cache(maxsize=1)
def template_bank():
    templates=glyph_templates()
    if not templates:return None
    vectors=np.stack([v.ravel() for _,v,_ in templates])
    energy=np.einsum('ij,ij->i',vectors,vectors)
    ratios=np.asarray([r for _,_,r in templates],dtype=np.float32)
    characters=[{'O':'0','o':'0','I':'1','l':'1'}.get(c,c) for c,_,_ in templates]
    groups={c:np.asarray([i for i,k in enumerate(characters) if k==c]) for c in set(characters)}
    return vectors,energy,ratios,groups


def match_glyph(mask):
    reference = normalize(mask)
    if reference is None:
        return []
    bank=template_bank()
    if bank is None:return []
    vectors,energy,ratios,groups=bank
    reference=reference.ravel()
    similarity=2*np.einsum('ij,j->i',vectors,reference)/(np.sum(reference**2)+energy)
    aspect=mask.shape[1]/mask.shape[0]
    similarity-=np.minimum(.12,.035*np.abs(np.log(aspect/ratios)))
    scores={c:float(similarity[indices].max()) for c,indices in groups.items()}
    return sorted(scores.items(),key=lambda pair:pair[1],reverse=True)


def parse_label(text):
    # Do not reinterpret OCR's 'pm' as 'µm', or '40' as '10'.
    text = text.replace('μ','µ').replace(',','.').strip()
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(nm|µm|um|mm|pm)',text)
    if not match:
        return None
    value = float(match[1])
    factors = {'nm':1,'µm':1000,'um':1000,'mm':1e6,'pm':.001}
    nm = value*factors[match[2]]
    if not math.isfinite(nm) or nm<=0:
        return None
    return nm


def recognize_region(region):
    if region is None:
        return {'status':'找不到独立的标尺文字区域','automatic':False}
    box, mask = region
    parts = components(mask)
    glyphs=[]
    height = mask.shape[0]
    for bounds, glyph in parts:
        x0,y0,x1,y1 = bounds
        if y1-y0 <= height*.25 and x1-x0 <= height*.25 and y0 >= height*.55:
            glyphs.append({'character':'.','score':1.0,'margin':1.0,'box':bounds})
            continue
        matches = match_glyph(glyph)
        if len(matches)<2:
            return {'status':'系统缺少可用字体模板','label_box':box,'automatic':False}
        (char,score),(_,runner_up) = matches[:2]
        # Monospaced serif instrument fonts can join µ and m at the baseline.
        # Evaluate split positions by shape instead of treating the joined word
        # as a single arbitrary letter.
        if glyph.shape[1]/glyph.shape[0]>1.55 and score<.90:
            splits=[]
            for cut in range(max(2,int(glyph.shape[1]*.25)),min(glyph.shape[1]-2,int(glyph.shape[1]*.75))):
                pair=[]
                for offset,part in ((0,glyph[:,:cut]),(cut,glyph[:,cut:])):
                    ys,xs=np.where(part)
                    if len(xs)<3:break
                    left,right,top,bottom=int(xs.min()),int(xs.max()+1),int(ys.min()),int(ys.max()+1)
                    choices=match_glyph(part[top:bottom,left:right])
                    if len(choices)<2:break
                    pair.append({'character':choices[0][0],'score':round(choices[0][1],4),
                                 'margin':round(choices[0][1]-choices[1][1],4),
                                 'box':(x0+offset+left,y0+top,x0+offset+right,y0+bottom)})
                if len(pair)==2:splits.append(pair)
            if splits:
                best=max(splits,key=lambda pair:min(g['score'] for g in pair))
                if min(g['score'] for g in best)>.90 and min(g['margin'] for g in best)>.04:
                    glyphs.extend(best)
                    continue
        glyphs.append({'character':char,'score':round(score,4), 'margin':round(score-runner_up,4),
                       'alternatives':[(c,round(s,4)) for c,s in matches[:3]], 'box':bounds})
    text=''.join(g['character'] for g in glyphs)
    nm=parse_label(text)
    score=min((g['score'] for g in glyphs),default=0)
    margin=min((g['margin'] for g in glyphs),default=0)
    # These are shape-match criteria, not a statistical probability of accuracy.
    automatic = nm is not None and score>=.90 and margin>=.085
    return {'method':'系统字体形状匹配','text':text,'value_nm':nm,'score':score,'margin':margin,
            'label_box':box,'glyphs':glyphs,'automatic':automatic,
            'status':'形状匹配通过' if automatic else '形状匹配不够明确，需核对或使用系统 OCR'}


def read_label(image, footer, bar, label_box=None, dark_text=False):
    # Two foreground thresholds preserve antialiased diagonal strokes after
    # resizing, without reducing the character-match acceptance criteria.
    variants=[]
    thresholds=(100,150)
    if label_box:
        values=np.asarray(image.convert('L').crop(label_box))
        if dark_text:values=255-values
        background=float(np.percentile(values,30))
        if background>100:
            thresholds=(min(235,int(background+60)),min(250,int(background+90)))
    for threshold in thresholds:
        if label_box:
            a=np.asarray(image.convert('L').crop(label_box))
            mask=(a<255-threshold) if dark_text else (a>threshold)
            result=recognize_region((label_box,mask))
        else:
            result=recognize_region(label_region(image,footer,bar,threshold))
        result['foreground_threshold']=threshold
        variants.append(result)
    accepted=[r for r in variants if r.get('automatic')]
    # Only ignore ambiguity between equivalent spellings of the same unit.
    if not accepted:
        for result in variants:
            gs=result.get('glyphs',[])
            if (result.get('value_nm') is not None and gs and
                all(g['score']>=.96 and (g['margin']>=.085 or
                    (g['character'] in ('µ','u') and g['margin']>=.06 and
                     len(g.get('alternatives',[]))>1 and g['alternatives'][1][0] in ('µ','u'))) for g in gs)):
                result['automatic']=True
                result['status']='高形状匹配通过（微米字符）'
        accepted=[r for r in variants if r.get('automatic')]
    best=max(accepted or variants,key=lambda r:r.get('score',0)).copy()
    best['threshold_checks']=[{'threshold':r['foreground_threshold'],'text':r.get('text'),
                               'score':r.get('score'),'automatic':r['automatic']} for r in variants]
    if len({r['value_nm'] for r in accepted})>1:
        best['automatic']=False
        best['status']='不同预处理识别出不同数值，需核对'
    return best


def ocr_variants(image, box, dark_text=False):
    """Clean text-only, padded variants; exclude all scale-line strokes."""
    label=image.convert('L').crop(box)
    result=[]
    for factor in (2,4):
        up=label.resize((label.width*factor,label.height*factor),Image.Resampling.LANCZOS)
        black=up if dark_text else ImageOps.invert(up)
        result.append(ImageOps.expand(black,border=24,fill=255).convert('RGB'))
    return result
