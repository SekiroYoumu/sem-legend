"""Measure optical recognition with all metadata deliberately ignored."""
import csv
import io
import sys
import time
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageOps

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from semlegend.core import analyze,detect_footer,find_bar,load_image,metadata_scale
from semlegend.recognition import read_label
from semlegend.samples import ORIGINAL_EXAMPLES

out=ROOT/'validation_output'/'recognition'
out.mkdir(parents=True,exist_ok=True)
rows=[]
files=sorted(ORIGINAL_EXAMPLES.glob('*.tif'))
temporary=tempfile.TemporaryDirectory(prefix='semlegend-robustness-')
sheet=Image.new('RGB',(960,130*len(files)),'#20242b')
draw=ImageDraw.Draw(sheet)
started=time.perf_counter()
for i,p in enumerate(files):
    image,_=load_image(p)
    baseline,_=metadata_scale(p)
    for variant in ('original','resize_150','jpeg_85'):
        factor=1
        if variant=='resize_150':
            factor=1.5
            sample=image.resize((1536,1152),Image.Resampling.LANCZOS)
        elif variant=='jpeg_85':
            buffer=io.BytesIO();image.save(buffer,format='JPEG',quality=85);buffer.seek(0)
            with Image.open(buffer) as decoded:sample=decoded.convert('RGB')
        else:sample=image
        clean=Path(temporary.name)/'input.png'
        Image.fromarray(np.asarray(sample)).save(clean)
        analysis=analyze(clean)
        footer=analysis.crop_bottom
        optical=analysis.recognition
        bar=optical.get('bar_line')
        scale=analysis.nm_per_pixel
        error=abs(scale*factor-baseline)/baseline if scale and baseline else None
        rows.append({'file':p.name,'variant':variant,'text':optical.get('text',''),
                     'automatic':bool(scale and not analysis.requires_confirmation),'shape_score':optical.get('score'),
                     'ambiguity_margin':optical.get('margin'),'bar_pixels':bar[0] if bar else None,
                     'nm_per_pixel':scale,'relative_error_vs_metadata':error})
        if variant=='original':
            region=sample.crop((0,footer,290,sample.height)).resize((580,154),Image.Resampling.NEAREST)
            region=ImageOps.contain(region,(580,120))
            sheet.paste(region,(0,i*130))
            # ASCII in artifact annotations avoids system-font dependencies.
            text=optical.get('text','').replace('µ','um')
            draw.text((600,i*130+10),p.name,fill='white')
            draw.text((600,i*130+32),f'label: {text}; bar: {bar[0]} px',fill='white')
            draw.text((600,i*130+54),f'match: {optical.get("score",0):.3f}; automatic: {optical.get("automatic",False)}',fill='#55e5c1')
            draw.text((600,i*130+76),f'optical scale: {scale:.5f} nm/px' if scale else 'scale: unknown',fill='white')
with (out/'benchmark.csv').open('w',newline='',encoding='utf-8-sig') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
sheet.save(out/'evidence.png')
for variant in ('original','resize_150','jpeg_85'):
    group=[r for r in rows if r['variant']==variant]
    accepted=[r for r in group if r['automatic']]
    errors=[r['relative_error_vs_metadata'] for r in accepted if r['relative_error_vs_metadata'] is not None]
    print(variant,'automatic',len(accepted),'/',len(group),'max scale error',max(errors,default=0))
print('elapsed_seconds',round(time.perf_counter()-started,3))
print('CSV:',out/'benchmark.csv')
temporary.cleanup()
