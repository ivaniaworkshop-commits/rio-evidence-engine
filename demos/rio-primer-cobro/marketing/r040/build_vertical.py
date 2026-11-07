#!/usr/bin/env python3
"""Responsive 9:16 remaster of locally illustrated 16:9 R040 scenes. No new factual claims."""
import json, subprocess, hashlib, math, sys
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_video import SCENES, ROOT, ASSETS, AUD, tstamp, astamp, font, wrap
DIR=ROOT/'vertical';DIR.mkdir(exist_ok=True)
W,H=720,1280;FPS=24

def draw_frame(scene):
  bg=Image.new('RGB',(W,H))
  px=bg.load()
  for y in range(H):
    t=y/H
    col=(int(6+4*t),int(35+36*t),int(54+26*t))
    ImageDraw.Draw(bg).line([(0,y),(W,y)],fill=col)
  d=ImageDraw.Draw(bg)
  d.rounded_rectangle((24,31,W-24,91),radius=24,fill='#0D4E5D')
  d.text((48,62),'RÍO · PRIMER COBRO',font=font(28,'heavy'),fill='#55E0CC',anchor='lm')
  d.text((W-46,62),f"{scene['id']:02d}/09",font=font(25,'bold'),fill='#CDEDF1',anchor='rm')
  d.text((42,129),scene['label'],font=font(23,'heavy'),fill='#FFC873')
  title=wrap(scene['title'],W-84,55,'heavy');y=176
  for line in title:
    d.text((42,y),line,font=font(55,'heavy'),fill='#FFFFFF');y+=61
  y=max(y+16,300)
  for ln in wrap(scene['subtitle'],W-86,27,'regular'):
    d.text((42,y),ln,font=font(27,'regular'),fill='#D0E4EA');y+=39
  d.rounded_rectangle((36,388,W-36,460),radius=18,fill='#095B66',outline='#25A7A6',width=2)
  metric_lines=wrap(scene['accent'],W-96,31,'heavy')
  for i,line in enumerate(metric_lines[:2]):
    d.text((58,402+33*i),line,font=font(31,'heavy'),fill='#53DECA')
  base=Image.open(ASSETS/f"scene_{scene['id']:02d}.png").convert('RGB')
  crop=base.crop((949,101,1547,815))
  crop.thumbnail((530,575),Image.Resampling.LANCZOS)
  ix=(W-crop.width)//2;iy=480
  d.rounded_rectangle((ix-12,iy-12,ix+crop.width+12,iy+crop.height+12),radius=30,fill='#144D60',outline='#368B98',width=3)
  bg.paste(crop,(ix,iy))
  d=ImageDraw.Draw(bg)
  safety=('QR DEMO · NO PAGABLE' if scene['screen']=='qr' else
      'EFECTIVO DECLARADO · NO BANCO' if scene['screen']=='cash' else
      'TICKET DE PRÁCTICA · NO CFDI' if scene['screen']=='ticket' else
      'DATOS LOCALES · SIN NUBE' if scene['screen']=='offline' else
      'DEMO EDUCATIVA · SIN PAGOS REALES')
  d.rounded_rectangle((35,1077,W-35,1129),radius=17,fill='#073849',outline='#50788B',width=2)
  d.text((W/2,1103),safety,font=font(22,'heavy'),fill='#FFD193',anchor='mm')
  d.text((W/2,1153),'RECREACIÓN VISUAL · NO CAPTURA REAL',font=font(18,'medium'),fill='#A7C9CE',anchor='mm')
  bg.save(DIR/f'frame_{scene["id"]:02d}.png',optimize=True)

def portrait_ass():
    data=(ROOT/'RIO_PRIMER_COBRO_SUBTITULOS_R040.ass').read_text()
    data=data.replace('PlayResX: 1280','PlayResX: 720').replace('PlayResY: 720','PlayResY: 1280')
    data=data.replace('Style: Main,Lato,35,','Style: Main,Lato,30,')
    data=data.replace(',2,50,50,44,1',',2,34,34,18,1')
    (DIR/'portrait_subtitles.ass').write_text(data)

def run(args):
    r=subprocess.run(args,capture_output=True,text=True)
    if r.returncode: print(r.stderr[-3000:]);raise RuntimeError(str(args))

def render():
   clips=[]
   for s in SCENES:
     p=DIR/f'clip_{s["id"]:02d}.mp4'
     dur=s['duration'];vf=f"zoompan=z='min(zoom+0.00011,1.04)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s=720x1280:fps=24,fade=t=in:st=0:d=0.3,fade=t=out:st={dur-0.3}:d=0.3,format=yuv420p"
     run(['ffmpeg','-hide_banner','-loglevel','error','-threads','3','-y','-loop','1','-framerate','24','-i',str(DIR/f'frame_{s["id"]:02d}.png'),'-t',str(dur),'-vf',vf,'-r','24','-c:v','libx264','-preset','veryfast','-crf','21','-pix_fmt','yuv420p','-an',str(p)])
     clips.append(p)
   listing=DIR/'list.txt';listing.write_text(''.join(f"file '{p.resolve()}'\n" for p in clips))
   silent=DIR/'video_no_audio.mp4'
   run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(silent)])
   target=ROOT/'RIO_PRIMER_COBRO_VERTICAL_120S_R040.mp4'
   run(['ffmpeg','-hide_banner','-loglevel','error','-threads','3','-y','-i',str(silent),'-i',str(AUD/'final_mix_120s.wav'),'-vf',f"ass={DIR/'portrait_subtitles.ass'}",'-c:v','libx264','-preset','veryfast','-crf','21','-c:a','aac','-b:a','160k','-movflags','+faststart','-t','120','-shortest',str(target)])
   doc=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(target)]))
   streams=doc['streams'];v=next(x for x in streams if x['codec_type']=='video');a=next(x for x in streams if x['codec_type']=='audio')
   dur=float(doc['format']['duration'])
   assert abs(dur-120)<0.08 and v['width']==720 and v['height']==1280 and v['codec_name']=='h264' and a['codec_name']=='aac'
   receipt={'file':target.name,'duration':dur,'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'pixels':'720x1280','video_codec':'h264','audio_codec':'aac','scenes':9,'description':'Mobile-first portrait composition, locally recreated interface and offline synthetic voice; no actual payments or captures.'}
   (ROOT/'reports'/'R040_VERTICAL_QA.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
   print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':
 for s in SCENES:draw_frame(s)
 portrait_ass();render()
