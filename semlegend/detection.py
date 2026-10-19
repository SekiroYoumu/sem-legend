"""Geometric candidates for horizontal SEM scale bars; no model dependency."""
import numpy as np

from .recognition import runs


def grid_footer(image):
    a=np.asarray(image.convert('L'))
    h,w=a.shape
    for y in range(int(h*.7),h-12):
        # FEI grid-style data bars have full-width horizontal rules and several
        # vertical cell borders; a uniform specimen alone is not sufficient.
        if (a[y]>160).mean()>.85:
            band=a[y+1:min(h-1,y+max(22,int(h*.09)))]
            if len(band)<10:continue
            columns=(band>150).mean(axis=0)>.65
            vertical=runs(columns)
            if len(vertical)>=4 and (band<100).mean()>.60 and (band>150).mean()>.02:
                return y
    medians=np.median(a,axis=1)
    flat=(np.abs(a.astype(np.float32)-medians[:,None])<=6).mean(axis=1)
    for y in range(int(h*.7),int(h*.97)):
        if medians[y]<100 and flat[y]>.90 and flat[max(0,y-2)]<.65:
            band=a[y:min(h,y+max(24,int(h*.07)))]; bright=band>180
            xs=np.where(bright.any(axis=0))[0]
            if (len(xs)>0 and xs[-1]-xs[0]>w*.65 and bright.mean()>.004 and
                np.mean(flat[y:y+len(band)]>.72)>.65):
                return y
    return h


def words(image,box,dark=False):
    x0,y0,x1,y1=map(int,box)
    x0=max(0,x0);y0=max(0,y0);x1=min(image.width,x1);y1=min(image.height,y1)
    if x1-x0<8 or y1-y0<4:return []
    a=np.asarray(image.convert('L'))[y0:y1,x0:x1]
    threshold=min(240,max(150,float(np.percentile(a,30))+40))
    mask=(a<100) if dark else (a>threshold)
    # Suppress horizontal frame rules, preserving individual glyph rows.
    mask=mask.copy();mask[mask.mean(axis=1)>.8]=False
    boxes=[]
    for lo,hi in runs(mask.any(axis=1)):
        if hi-lo<4:continue
        parts=runs(mask[lo:hi].any(axis=0))
        groups=[]
        for left,right in parts:
            if groups and left-groups[-1][1]<=max(2,(hi-lo)*.6):groups[-1]=(groups[-1][0],right)
            else:groups.append((left,right))
        for left,right in groups:
            if right-left>=max(8,hi-lo) and right-left<image.width*.4:
                boxes.append((max(x0+left-1,0),max(y0+lo-1,0),min(x0+right+1,image.width),min(y0+hi+1,image.height)))
    return boxes


def split_candidates(image):
    """FEI-style two collinear strokes separated by a centred scale label."""
    a=np.asarray(image.convert('L'));h,w=a.shape
    results=[];seen=[]
    minimum=max(10,int(w*.035))
    for y in range(int(h*.75),h-3):
        segments=[(x0,x1) for x0,x1 in runs(a[y]>180) if minimum<=x1-x0<=w*.5]
        for (x0,x1),(x2,x3) in zip(segments,segments[1:]):
            gap=x2-x1;left=x1-x0;right=x3-x2
            if not max(8,w*.015)<=gap<=w*.2 or not .45<=left/right<=2.2:continue
            if x3-x0>w*.65 or x0<w*.3:continue
            if any(abs(y-yy)<5 and abs(x0-xx)<5 for xx,yy in seen):continue
            radius=max(5,min(int(gap*.4),int(h*.025)))
            labels=words(image,(x1,y-radius,x2,y+radius+1))
            labels=[b for b in labels if b[1]<=y+2 and b[3]>=y-2]
            if not labels:continue
            # Centre the terminal ticks, excluding the ends' stroke thickness.
            endpoints=[]
            for edge in (x0,x3-1):
                xx0=max(0,edge-3);xx1=min(w,edge+4)
                region=a[max(0,y-3):min(h,y+4),xx0:xx1]>180
                support=region.sum(axis=0)
                strong=np.where(support>=max(4,region.shape[0]-.5))[0]
                endpoints.append(float(xx0+strong.mean()) if len(strong) else float(edge))
            length=round(endpoints[1]-endpoints[0])
            for box in labels:
                results.append({'bar':(length,round(endpoints[0]),y),'label_box':box,
                                'layout':'中间文字分段标尺','dark_text':False})
            seen.append((x0,y))
    return results


def solid_candidates(image,footer):
    """Solid bars in databar cells, or black/white corner annotation boxes."""
    a=np.asarray(image.convert('L'));h,w=a.shape
    results=[]
    for dark in (False,True):
        mask=a<70 if dark else a>235
        seen=[]
        start=footer if footer<h else int(h*.80)
        for y in range(start,h-2):
            segments=[(l,r) for l,r in runs(mask[y]) if max(18,w*.025)<=r-l<=w*.6]
            for left,right in segments:
                if any(abs(left-l)<4 and abs(y-yy)<max(5,int(h*.035)) for l,yy in seen):continue
                # The fill should be a rectangle rather than specimen texture.
                down=y
                while down<h and mask[down,left:right].mean()>.97:down+=1
                thickness=down-y
                if not 2<=thickness<=min((right-left)/4,h*.04):continue
                width=right-left
                surround=np.r_[mask[max(0,y-3):y,left:right].ravel(),mask[down:min(h,down+3),left:right].ravel()]
                if len(surround)==0 or surround.mean()>.35:continue
                radius=max(18,min(int(width),int(h*.14)))
                top_limit=footer if footer<h else int(h*.7)
                bounds=[(left-width*.75,max(top_limit,y-radius),right+width*.75,y-1),
                        (left-width*.75,down+1,right+width*.75,down+radius),
                        (right+2,max(top_limit,y-radius*.3),min(w,right+w*.3),down+radius*.3),
                        (max(0,left-w*.3),max(top_limit,y-radius*.3),left-2,down+radius*.3)]
                if dark:
                    panels=[]
                    for yy in (max(0,y-2),min(h-1,down+2)):
                        panels.extend((l,r) for l,r in runs(a[yy]>230) if l<=left and r>=right)
                    if panels:
                        pl,pr=min(panels,key=lambda p:p[1]-p[0])
                        bounds=[(max(b[0],pl+1),b[1],min(b[2],pr-1),b[3]) for b in bounds]
                for search in bounds:
                    for box in words(image,search,dark):
                        results.append({'bar':(width,left,(y+down-1)//2),'label_box':box,
                                        'layout':'实心横条（黑色）' if dark else '实心横条（白色）','dark_text':dark})
                seen.append((left,y))
    return results


def bracket_candidates(image):
    """Thin H/U-ended bars, including top-left overlays and grey data bars."""
    a=np.asarray(image.convert('L'));h,w=a.shape
    mask=a>100
    searchmask=mask.copy()
    searchmask[1:] |= mask[:-1]
    searchmask[:-1] |= mask[1:]
    results=[];seen=[]
    rows=list(range(2,int(h*.2)))+list(range(int(h*.72),h-2))
    radius=max(8,int(h*.035))
    for y in rows:
        for left,right in runs(searchmask[y]):
            length=right-left-1
            if not max(25,w*.04)<=length<=w*.6:continue
            if any(abs(left-x)<5 and abs(y-yy)<radius for x,yy in seen):continue
            y0=max(0,y-radius);y1=min(h,y+radius)
            centres=[];supports=[]
            for edge in (left,right-1):
                x0=max(0,edge-2);x1=min(w,edge+3)
                support=mask[y0:y1,x0:x1].sum(axis=0)
                best=int(support.max());xx=np.where(support==best)[0]
                supports.append(best);centres.append(x0+float(xx.mean()))
            body=mask[y0:y1,left+4:right-4].mean()
            if min(supports)<max(6,int(h*.008)) or body>.30:continue
            gap=max(20,int(h*.08))
            boxes=words(image,(left-length*.2,max(0,y-gap),right+length*.2,y-2))
            # A label needs several glyphs; bare tick runs do not calibrate.
            for box in boxes:
                results.append({'bar':(round(centres[1]-centres[0]),round(centres[0]),y),
                                'label_box':box,'layout':'细线端点标尺（上方文字）','dark_text':False})
            if boxes:seen.append((left,y))
    return results
