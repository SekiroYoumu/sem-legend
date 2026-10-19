"""Evaluate real SEM samples after physically removing all metadata."""
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw,ImageOps

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from semlegend.core import analyze,load_image,metadata_scale,render,Settings
from semlegend.samples import ORIGINAL_EXAMPLES

out=ROOT/'validation_output'/'compatibility'
out.mkdir(parents=True,exist_ok=True)
expected={
    '4.tif':100000,'5.tif':10000,'6.tif':10000,
    'FEI-Helios-Ebeam-8bits.tif':500000,'FEI-Helios-Ebeam-16bits.tif':500000,
    'FEI_Quanta_screenshot_crop.png':100000,'cu_catalyst.jpg':5000,
    'fei_nova_nanocigarette.png':500,'jeol_neoscope_shell.jpg':20000,
    'silver_nanowires.jpg':1000,'tescan_mira_1.jpg':500000,
    'tescan_mira_2.jpg':500000,'tescan_mira_3.jpg':500000,
    'processed_black_bar.png':50000,
}
negative={'FEI-Helios-navcam-with-no-IRBeam-bad-floats.tif','FEI-Helios-navcam-with-no-IRBeam.tif','FEI-Helios-navcam.tif'}
files=list(ORIGINAL_EXAMPLES.glob('*.tif'))
files += [p for p in (ROOT/'validation_output'/'public_sem').glob('*') if p.name in expected]
files += [p for p in (ROOT/'validation_output'/'fei_samples').glob('*') if p.name in expected or p.name in negative]
files=sorted(files,key=lambda p:p.name)
rows=[];images=[]
for i,p in enumerate(files):
    im,_=load_image(p)
    stripped=out/f'input_{i:02d}.png'
    Image.fromarray(np.asarray(im)).save(stripped)
    assert metadata_scale(stripped)[0] is None
    a=analyze(stripped)
    r=a.recognition
    reference,_=metadata_scale(p)
    label_nm=r.get('value_nm')
    if label_nm is None and a.nm_per_pixel and a.bar_pixels:label_nm=a.nm_per_pixel*a.bar_pixels
    truth=expected.get(p.name)
    if truth is not None and label_nm is not None:
        assert abs(truth-label_nm)<1e-8,(p.name,label_nm,truth)
    tier='automatic' if a.nm_per_pixel and not a.requires_confirmation else ('review' if a.nm_per_pixel else 'unrecognized')
    if p.name in negative:assert a.nm_per_pixel is None,'Scale invented for a negative control'
    difference=abs(a.nm_per_pixel-reference)/reference if a.nm_per_pixel and reference else None
    row=dict(file=p.name,tier=tier,negative_control=p.name in negative,label=r.get('text',''),expected_label_nm=truth,
             recognized_label_nm=label_nm,nm_per_pixel=a.nm_per_pixel,bar_pixels=a.bar_pixels,
             layout=r.get('layout',''),crop_y=a.crop_bottom,shape_score=r.get('score'),
             ambiguity_margin=r.get('margin'),relative_error_vs_metadata=difference)
    rows.append(row)
    (out/f'record_{i:02d}.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    if tier=='automatic':
        processed,_=render(a,Settings())
        processed.save(out/f'output_{i:02d}.png')
    top=max(0,a.crop_bottom-10) if a.crop_bottom<a.height else int(a.height*.75)
    line=r.get('bar_line');box=r.get('label_box')
    if line:
        x0=max(0,min(line[1],box[0] if box else line[1])-15)
        x1=min(im.width,max(line[1]+line[0],box[2] if box else line[1]+line[0])+15)
        y0=max(0,min(line[2],box[1] if box else line[2])-15)
        y1=min(im.height,max(line[2],box[3] if box else line[2])+20)
        roi=im.crop((x0,y0,x1,y1))
    else:roi=im.crop((0,top,im.width,im.height))
    roi=ImageOps.contain(roi.convert('RGB'),(650,115),Image.Resampling.NEAREST)
    images.append(roi)
    print(p.name,tier,r.get('text',''),a.bar_pixels,flush=True)
with (out/'results.csv').open('w',newline='',encoding='utf-8-sig') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
sheet=Image.new('RGB',(1100,len(rows)*130),'#24282e');draw=ImageDraw.Draw(sheet)
for i,(row,roi) in enumerate(zip(rows,images)):
    sheet.paste(roi,(0,i*130))
    draw.text((680,i*130+5),row['file'],fill='white')
    draw.text((680,i*130+30),row['tier']+' / '+row['label'].replace('µ','um'),fill='#55e5c1' if row['tier']=='automatic' else '#ffc171')
    if row['nm_per_pixel']:
        draw.text((680,i*130+55),f"{row['nm_per_pixel']:.6g} nm/px; {row['bar_pixels']} px",fill='white')
sheet.save(out/'evidence.png')
print('TOTAL',len(rows),{tier:sum(row['tier']==tier for row in rows) for tier in ['automatic','review','unrecognized']})
