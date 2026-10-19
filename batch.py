"""Optional headless batch entry point; the desktop app does not need this."""
import argparse
import csv
from pathlib import Path

from semlegend.core import EXTENSIONS, Settings, analyze, export_image


def main():
    parser = argparse.ArgumentParser(description='本地 SEM 图像批量整理')
    parser.add_argument('input', type=Path)
    parser.add_argument('--output', type=Path, default=Path('output'))
    parser.add_argument('--no-bar', action='store_true')
    parser.add_argument('--no-ocr', action='store_true')
    parser.add_argument('--format', choices=['PNG','TIFF'], default='PNG')
    parser.add_argument('--preset', type=Path)
    args=parser.parse_args()
    settings=Settings()
    if args.preset:
        import json
        settings=Settings(**json.loads(args.preset.read_text(encoding='utf-8')))
    settings.output_format=args.format
    if args.no_bar: settings.add_bar=False
    paths=sorted(p for p in args.input.rglob('*') if p.is_file() and p.suffix.lower() in EXTENSIONS) if args.input.is_dir() else [args.input]
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for path in paths:
        try:
            a=analyze(path,use_ocr=not args.no_ocr)
            out,report=export_image(a,settings,args.output)
            rows.append({'input':str(path),'output':str(out),'status':'OK','message':report['warnings']})
            print('OK',path.name)
        except Exception as e:
            rows.append({'input':str(path),'output':'','status':'FAILED','message':str(e)})
            print('FAILED',path.name,str(e))
    from datetime import datetime
    log=args.output/('batch_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.csv')
    with log.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=['input','output','status','message']);writer.writeheader();writer.writerows(rows)
    return 1 if any(r['status']=='FAILED' for r in rows) else 0


if __name__=='__main__':
    raise SystemExit(main())
