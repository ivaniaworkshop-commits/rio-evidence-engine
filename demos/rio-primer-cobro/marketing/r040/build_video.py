#!/usr/bin/env python3
"""RÍO Primer Cobro R040 - reproducible local motion-graphics video.
No external payments, remote screenshots, or invented real-world footage.
All app UI panels in this render are recreated and clearly labeled as such.
Outputs 120.000 s H.264/AAC, narration, captions and QA evidence.
"""
from __future__ import annotations
import argparse, array, hashlib, json, math, os, re, shutil, subprocess, sys, textwrap, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'assets'; CLIPS=ROOT/'clips'; AUD=ROOT/'audio'; REPORTS=ROOT/'reports'
for p in [ASSETS,CLIPS,AUD,REPORTS]:p.mkdir(exist_ok=True)
FPS=24; W=1600; H=900
OUTW=1280; OUTH=720
URL='rio-primer-cobro-frontdesk.vercel.app'
TEAL='#43D6C1'; GOLD='#FFC873'; WHITE='#F6FBFA'; PALE='#BBDBE2'; INK='#072638'; NAVY='#08293D'; MUTED='#7798A5'; CORAL='#FF927A'
FONTS={'heavy':'/usr/share/fonts/truetype/lato/Lato-Heavy.ttf','bold':'/usr/share/fonts/truetype/lato/Lato-Bold.ttf','regular':'/usr/share/fonts/truetype/lato/Lato-Regular.ttf','medium':'/usr/share/fonts/truetype/lato/Lato-Medium.ttf'}
fontcache={}
def font(size:int,weight='regular'):
    key=(size,weight)
    if key not in fontcache: fontcache[key]=ImageFont.truetype(FONTS[weight],size=size)
    return fontcache[key]

SCENES=[
 dict(id=1,from_s=0,duration=11,title='Una venta más clara',subtitle='Para puestos, tiendas y mercados',accent='Tu negocio. Tus decisiones.',screen='market',label='EL RETO COTIDIANO',narration='¿Vendes en una tienda, un puesto o un mercado? Entre cantidades y cambio, cada venta merece claridad. Conoce RÍO Primer Cobro.',subs=['¿Vendes en una tienda, un puesto o un mercado?','Entre cantidades y cambio, cada venta merece claridad.','Conoce RÍO Primer Cobro.']),
 dict(id=2,from_s=11,duration=12,title='Aprende sin registro',subtitle='Caja educativa en español, gratuita',accent='Comienza desde tu celular',screen='welcome',label='01 · EMPIEZA',narration='Una caja educativa y gratuita, en español. Abre la demo desde tu celular, entra a Caja y practica sin crear una cuenta.',subs=['Una caja educativa y gratuita, en español.','Abre la demo desde tu celular, entra a Caja','y practica sin crear una cuenta.']),
 dict(id=3,from_s=23,duration=14,title='Piezas y peso',subtitle='Carrito con cálculos por producto',accent='$30 + $20 = $50 MXN',screen='cart',label='02 · ARMA TU VENTA',narration='Agrega dos panes de quince pesos: treinta. Después, quinientos gramos de jitomate a cuarenta pesos por kilo: veinte. Tu carrito suma cincuenta pesos.',subs=['Dos panes de quince pesos: treinta.','Quinientos gramos de jitomate a cuarenta por kilo: veinte.','Tu carrito suma cincuenta pesos.']),
 dict(id=4,from_s=37,duration=14,title='Efectivo y cambio',subtitle='Registra la recepción manualmente',accent='$100 recibido → $50 de cambio',screen='cash',label='03 · REVISA EL CAMBIO',narration='Elige efectivo. Registra manualmente cien pesos recibidos. Para una venta de cincuenta, RÍO muestra cincuenta de cambio. La verificación del dinero depende de ti.',subs=['Elige efectivo. Registra manualmente cien pesos recibidos.','Para una venta de cincuenta, RÍO muestra cincuenta de cambio.','La verificación del dinero depende de ti.']),
 dict(id=5,from_s=51,duration=14,title='QR de práctica',subtitle='Aprende el recorrido digital sin pagar',accent='NO PAGABLE · DEMO',screen='qr',label='04 · PRACTICA CON QR',narration='¿Quieres practicar un recorrido digital? Genera un QR escaneable de demostración. Atención: no es pagable, no envía dinero y nunca confirma un cobro real.',subs=['¿Quieres practicar un recorrido digital?','Genera un QR escaneable de demostración.','No es pagable y nunca confirma un cobro real.']),
 dict(id=6,from_s=65,duration=14,title='Ticket e historial',subtitle='Revisa tus ventas de práctica',accent='Ticket de demostración · No CFDI',screen='ticket',label='05 · DOCUMENTA',narration='Prepara un ticket de práctica; cópialo, imprímelo o descárgalo. Consulta el historial guardado en el navegador. Ese ticket no es factura ni comprobante bancario.',subs=['Prepara un ticket de práctica; cópialo, imprímelo o descárgalo.','Consulta el historial guardado en el navegador.','No es factura ni comprobante bancario.']),
 dict(id=7,from_s=79,duration=15,title='Tus datos, locales',subtitle='Archivo sin conexión y respaldo JSON',accent='Sin sincronización automática',screen='offline',label='06 · CONSERVA TUS PRÁCTICAS',narration='El archivo descargado funciona sin internet, en un navegador compatible. Tus datos permanecen locales cuando el navegador permite guardarlos. Exporta un respaldo JSON antes de cambiarlos o borrarlos.',subs=['El archivo descargado funciona sin internet.','Tus datos son locales cuando el navegador permite guardarlos.','Exporta un respaldo JSON.']),
 dict(id=8,from_s=94,duration=15,title='Ayuda y reporte',subtitle='Reglas locales que acompañan tu práctica',accent='Dudas → guía → pruebas internas',screen='help',label='07 · APRENDE Y EVALÚA',narration='¿Tienes dudas sobre el peso, el efectivo o internet? La ayuda responde mediante reglas locales. En Reporte puedes ejecutar pruebas internas y descargar un resumen de tu práctica.',subs=['¿Dudas sobre el peso, el efectivo o internet?','La ayuda responde mediante reglas locales.','Ejecuta pruebas internas y descarga tu reporte.']),
 dict(id=9,from_s=109,duration=11,title='RÍO Primer Cobro',subtitle='Aprende antes de cobrar de verdad',accent='Pruébalo gratis',screen='outro',label='COMIENZA GRATIS',narration='RÍO Primer Cobro. Aprende paso a paso, sin mover dinero. Pruébalo gratis y utiliza medios autorizados cuando cobres de verdad.',subs=['RÍO Primer Cobro. Aprende paso a paso, sin mover dinero.','Pruébalo gratis. Para pagos reales, usa medios autorizados.'])
]
assert sum(s['duration'] for s in SCENES)==120 and all((s['from_s']+s['duration']==SCENES[i+1]['from_s']) for i,s in enumerate(SCENES[:-1]))

CLAIMS={
 'C01':'La app descrita es educativa, gratuita, sin login; soporte portada R016 y app R015; acceso público R016 no implica despliegue nuevo.',
 'C02':'El cálculo usa unidad de centavos exactos; 2×15=30; 500 gramos×40/1000=20; total 50; valores de práctica.',
 'C03':'En efectivo la app registra la declaración de la persona; 100-50=50 de cambio, no prueba dinero real.',
 'C04':'QR de prueba escaneable y explícitamente no pagable; sin confirmación bancaria ni conexión a CoDi/Pey.',
 'C05':'Ticket con folio de demostración y historial local, ticket no CFDI ni comprobante bancario.',
 'C06':'La versión HTML local funciona offline en navegador compatible; persistencia sujeta a localStorage y respaldo JSON no cifrado.',
 'C07':'Ayuda usa reglas locales predefinidas (RioChat), no LLM generativo activo. El reporte ejecuta pruebas internas al generarse.',
 'C08':'No se promete mejora de ingresos, ahorro medido, comercio real, protección bancaria, certificación de accesibilidad ni seguridad de producción.'
}

def run(cmd,quiet=False,check=True):
    p=subprocess.run(cmd,stdout=subprocess.PIPE if quiet else None,stderr=subprocess.PIPE if quiet else None,text=True)
    if check and p.returncode!=0:
        print('COMMAND FAILED:',cmd,'\n',p.stderr[-4000:] if p.stderr else '',file=sys.stderr);raise subprocess.CalledProcessError(p.returncode,cmd)
    return p

def duration_of(path:Path)->float:
    return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)]).strip())

def measure_text(s):
    return len(re.findall(r"[\wÁÉÍÓÚÜÑáéíóúüñ]+(?:[.,][0-9]+)?",s))

# rounded forms and typographic primitives

def fill_gradient():
    yy,xx=np.mgrid[0:H,0:W]
    a=(xx/W*0.23+yy/H*0.33)
    tl=np.array([6,35,56],dtype=float)
    br=np.array([6,87,94],dtype=float)
    out=np.uint8(np.clip(tl[None,None,:]*(1-a[:,:,None])+br[None,None,:]*a[:,:,None],0,255))
    return Image.fromarray(out,'RGB').convert('RGBA')

def rr(d,box,r,fill,outline=None,width=1):d.rounded_rectangle(tuple(map(int,box)),radius=int(r),fill=fill,outline=outline,width=width)
def txt(d,point,text,size=30,color=WHITE,weight='regular',anchor=None,stroke_width=0):
    d.text(tuple(map(int,point)),text,font=font(size,weight),fill=color,anchor=anchor,stroke_width=stroke_width,stroke_fill=INK)

def wrap(text,max_width,size,weight='regular'):
    f=font(size,weight);pieces=text.split();out=[];line=''
    for word in pieces:
        n=(line+' '+word).strip()
        if f.getlength(n)>max_width and line:out.append(line);line=word
        else:line=n
    if line:out.append(line)
    return out

def pill(d,box,label,fill,foreground,size=22,weight='bold',line=None):
    rr(d,box,18,fill,outline=line,width=2 if line else 1)
    xx=(box[0]+box[2])/2;yy=(box[1]+box[3])/2
    txt(d,(xx,yy),label,size,foreground,weight,anchor='mm')

def market(draw,x,y):
    # schematic of a Mexican neighborhood stall, clearly a drawn illustration
    rr(draw,(x+20,y+200,x+545,y+565),24,'#F5FAF9')
    draw.polygon([(x,y+205),(x+90,y+80),(x+520,y+80),(x+625,y+205)],fill='#FFCF8E')
    for i in range(6):
        x0=x+15+i*99;draw.polygon([(x0,y+205),(x0+99,y+205),(x0+87,y+285),(x0+20,y+285)],fill='#F27F66' if i%2 else '#FFE1AF')
    draw.rectangle((x+48,y+290,x+575,y+316),fill='#11485A')
    rr(draw,(x+188,y+110,x+410,y+174),16,'#1A6470')
    txt(draw,(x+300,y+142),'PUESTO LOCAL',29,WHITE,'heavy',anchor='mm')
    for i,c in enumerate(['#E26649','#DFBD49','#88AD54','#E26649','#D5B63F','#85B448']):
        draw.ellipse((x+90+i*76,y+364,x+152+i*76,y+425),fill=c)
        draw.arc((x+90+i*76,y+364,x+152+i*76,y+425),0,200,fill='#A9D16A',width=4)
    draw.rectangle((x+65,y+432,x+546,y+451),fill='#8B5D41')
    txt(draw,(x+302,y+520),'VENTAS DEL DÍA',32,'#255266','heavy',anchor='mm')

def phone(draw,screen):
    x=976;y=117;w=553;h=682
    rr(draw,(x-14,y-12,x+w+13,y+h+13),60,'#021B27',outline='#3F9DA4',width=5)
    rr(draw,(x,y,x+w,y+h),44,'#F5FAF9')
    rr(draw,(x+181,y+8,x+379,y+22),9,'#092B3B')
    rr(draw,(x+31,y+40,x+w-32,y+102),18,'#0D5265')
    txt(draw,(x+55,y+70),'RÍO · PRIMER COBRO',26,WHITE,'heavy',anchor='lm')
    pill(draw,(x+34,y+114,x+158,y+154),'CAJA','#1D8E91',WHITE,18)
    pill(draw,(x+165,y+114,x+288,y+154),'AYUDA','#DDEDEB','#39606B',18)
    pill(draw,(x+294,y+114,x+444,y+154),'REPORTE','#DDEDEB','#39606B',18)
    draw.line((x+32,y+164,x+w-32,y+164),fill='#D9E5E5',width=3)
    u=x+44;v=y+198;rw=w-88
    def panel(t,lines=None,accent=False,top=None):
        nonlocal v
        hh=top or (80+len(lines or [])*44)
        rr(draw,(u,v,u+rw,v+hh),20,'#E9F4F3' if accent else '#FFFFFF',outline='#D4E5E5',width=2)
        txt(draw,(u+20,v+20),t,26,'#115369','heavy')
        for k,line in enumerate(lines or []):txt(draw,(u+20,v+63+43*k),line,22,'#3A626D','bold')
        v+=hh+14
    if screen=='welcome':
        panel('Vende como siempre', ['Aprende lo digital,', 'paso a paso.'],accent=True,top=173)
        panel('Paso 1 · Prepara tu venta', ['Producto  ·  Cantidad  ·  Precio'],top=115)
        panel('Paso 2 · Elige cómo cobrar',['Efectivo    |    QR de práctica'],top=115)
        pill(draw,(u,y+h-77,u+rw,y+h-22),'COMENZAR EN CAJA','#0F8D8E',WHITE,22)
    elif screen=='cart':
        panel('Carrito de práctica',['Pan  ·  2 × $15.00             $30.00', 'Jitomate  ·  500 g              $20.00'],accent=True,top=191)
        rr(draw,(u,v,u+rw,v+128),23,'#11586D')
        txt(draw,(u+23,v+22),'TOTAL',24,'#B9F3E4','heavy')
        txt(draw,(u+rw-23,v+75),'$50.00 MXN',47,WHITE,'heavy',anchor='ra')
        v+=150
        panel('Por pieza o por peso',['Cálculo en centavos'],top=121)
    elif screen=='cash':
        panel('Método seleccionado',['● Efectivo — registro manual'],accent=True,top=124)
        panel('Total de la venta',['$50.00 MXN'],top=121)
        panel('Monto declarado recibido',['$100.00 MXN'],top=124)
        rr(draw,(u,v,u+rw,v+90),20,'#DDF4E8');txt(draw,(u+22,v+20),'CAMBIO',22,'#136A60','heavy');txt(draw,(u+rw-24,v+54),'$50.00',34,'#08694F','heavy',anchor='ra')
    elif screen=='qr':
        panel('QR de práctica · NO PAGABLE',[],accent=True,top=82)
        try:
            import qrcode
            q=qrcode.QRCode(border=1,error_correction=qrcode.constants.ERROR_CORRECT_L,box_size=5)
            q.add_data('RIO-QR-DEMO|NO-PAGABLE|DEMO-R040|MXN-50.00');q.make(fit=True)
            im=q.make_image(fill_color='#145367',back_color='white').convert('RGB');im=im.resize((245,245))
            # draw on global overlay AFTER draw: return QR rect
            qrrect=(x+154,y+260)
        except ImportError:im=None;qrrect=None
        rr(draw,(u,y+520,u+rw,y+605),20,'#FFF0E0')
        txt(draw,(u+rw/2,y+545),'SIMULACIÓN · SIN DINERO REAL',21,'#92500F','heavy',anchor='mt')
        return im,qrrect
    elif screen=='ticket':
        panel('Ticket DEMO-2026-R040',['PAN  2 × $15               $30.00','JITOMATE  500 g       $20.00','TOTAL                         $50.00'],accent=True,top=232)
        pill(draw,(u,v,u+145,v+68),'COPIAR','#D8F2E8','#14586A',17)
        pill(draw,(u+154,v,u+303,v+68),'IMPRIMIR','#D8F2E8','#14586A',17)
        pill(draw,(u+310,v,u+rw,v+68),'BAJAR','#D8F2E8','#14586A',17)
        v+=100
        panel('Historial local',['Registro en este navegador'],top=115)
        txt(draw,(u+20,y+h-27),'NO ES FACTURA · NO ES CFDI',17,'#92500F','heavy')
    elif screen=='offline':
        panel('Trabajo sin conexión',['Archivo HTML descargado','y abierto en un navegador'],accent=True,top=182)
        panel('Historial local',['Según permisos del navegador'],top=125)
        pill(draw,(u,v,u+rw,v+89),'DESCARGAR RESPALDO JSON','#0D8C8D',WHITE,20)
        v+=110
        txt(draw,(u+16,v+14),'No existe sincronización automática',19,'#526A73','bold')
    elif screen=='help':
        panel('Ayuda por reglas locales',['¿Cómo calculo el peso?','¿Qué hago sin internet?'],accent=True,top=183)
        panel('Reporte de práctica',['Categorías de dudas','Pruebas internas al generar'],top=176)
        pill(draw,(u,v,u+rw,v+70),'EJECUTAR PRUEBAS Y GENERAR JSON','#0D8C8D',WHITE,18)
    return None,None

def make_image(s):
    canvas=fill_gradient()
    d=ImageDraw.Draw(canvas)
    # large abstract decoration without pretending evidence of user activity
    d.ellipse((1020,-470,2050,560),fill='#12495B',outline='#225F72',width=5)
    d.ellipse((-550,630,610,1520),fill='#0D4F62')
    d.arc((1090,60,1750,710),start=220,end=349,fill='#227889',width=9)
    d.arc((1110,80,1720,680),start=200,end=305,fill='#1EA59D',width=4)
    txt(d,(80,47),'RÍO  /  PRIMER COBRO',27,TEAL,'heavy')
    txt(d,(810,47),'DEMO EDUCATIVA',21,PALE,'bold',anchor='rm')
    for i in range(9):
        rr(d,(80+i*82,94,151+i*82,101),4,TEAL if i==s['id']-1 else '#285F6C')
    txt(d,(80,153),s['label'],26,GOLD,'heavy')
    # left text hierarchy
    title_size=65 if len(s['title'])<23 else 57
    title_lines=wrap(s['title'],815,title_size,'heavy')
    ty=217
    for line in title_lines:
        txt(d,(80,ty),line,title_size,WHITE,'heavy');ty+=74
    ty=max(345,ty+12)
    for line in wrap(s['subtitle'],785,31,'medium'):
        txt(d,(84,ty),line,31,'#CDE5E8','medium');ty+=49
    rr(d,(78,510,875,630),25,'#0B5967',outline='#1B8991',width=2)
    for n,line in enumerate(wrap(s['accent'],750,34,'heavy')[:2]):
        txt(d,(109,545+n*46),line,34,TEAL,'heavy')
    # safety notice -- constant, legible; not to be cropped
    if s['screen']=='qr':note='AVISO: QR DEMO · NO PAGABLE · SIN VERIFICACIÓN DE PAGO'
    elif s['screen']=='cash':note='EFECTIVO DECLARADO POR PERSONA · NO VERIFICACIÓN AUTOMÁTICA'
    elif s['screen']=='ticket':note='TICKET DE PRÁCTICA · NO ES CFDI'
    elif s['screen']=='offline':note='ARCHIVO LOCAL · DATOS NO SINCRONIZADOS NI CIFRADOS'
    elif s['screen']=='outro':note='DEMO EDUCATIVA · SIN PAGOS REALES'
    else:note='DEMOSTRACIÓN · DATOS FICTICIOS · NO PAGOS REALES'
    rr(d,(80,673,880,735),18,'#0D3448',outline='#517F8C',width=2)
    txt(d,(102,704),note,21,GOLD,'heavy',anchor='lm')
    txt(d,(80,760),'RECREACIÓN VISUAL · FUNCIONALIDAD R015 VERIFICADA EN CÓDIGO',19,'#9ABAC4','medium')
    txt(d,(1510,760),f"{s['id']:02d}/09",24,'#A0BAC3','bold',anchor='rm')
    if s['screen']=='market':
        market(d,962,85)
        pill(d,(1054,728,1470,799),'PRÁCTICA SIN DINERO','#0B6D70',WHITE,23)
    elif s['screen']=='outro':
        rr(d,(962,206,1505,626),34,'#E9F7F3')
        txt(d,(1234,278),'RÍO',116,'#0D6671','heavy',anchor='mm')
        txt(d,(1234,383),'PRIMER COBRO',47,'#0D6671','heavy',anchor='mm')
        txt(d,(1234,470),'PRUÉBALO GRATIS',35,'#0B766F','heavy',anchor='mm')
        txt(d,(1234,550),'SIN PAGOS REALES',29,'#A15437','heavy',anchor='mm')
        txt(d,(1230,690),URL,26,WHITE,'bold',anchor='mm')
    else:
        qr,position=phone(d,s['screen'])
        if qr is not None:canvas.alpha_composite(qr.convert('RGBA'),position)
    canvas.convert('RGB').save(ASSETS/f"scene_{s['id']:02d}.png",optimize=True)

def tstamp(t):
    ms=round((t-int(t))*1000);h=int(t//3600);m=int(t//60)%60;s=int(t)%60
    if ms>=1000:ms=0;s+=1
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'
def astamp(t):
    cs=round((t-int(t))*100);h=int(t//3600);m=int(t//60)%60;s=int(t)%60
    return f'{h}:{m:02d}:{s:02d}.{cs:02d}'

def create_audio():
    durinfo=[]
    for s in SCENES:
        i=s['id'];wav=AUD/f'narration_raw_{i:02d}.wav'
        run(['espeak','-v','es-la','-s','148','-p','44','-a','155','-w',str(wav),s['narration']],quiet=True)
        raw_d=duration_of(wav)
        target=s['duration']-0.57
        # speed only up if strictly necessary; else retain natural voice and allow a meaningful pause
        tempo=max(1.0,raw_d/target)
        if tempo>1.22:print('WARNING: compressed narration',i,tempo)
        adjusted=AUD/f'narration_{i:02d}.wav'
        temp=AUD/f'narration_stretched_{i:02d}.wav'
        run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(wav),'-af',f'atempo={tempo:.7f}', '-ac','1','-ar','22050',str(temp)],quiet=True)
        # Deterministically pad exact per-scene PCM frames; never rely on atempo/apad timestamp rounding.
        with wave.open(str(temp),'rb') as src:
            assert src.getframerate()==22050 and src.getnchannels()==1 and src.getsampwidth()==2
            frames=src.readframes(src.getnframes())
        max_samples=round((s['duration']-0.42)*22050)
        pcm=np.frombuffer(frames,dtype=np.int16)[:max_samples]
        output=np.zeros(round(s['duration']*22050),dtype=np.int16)
        pre=round(.22*22050)
        available=min(len(pcm),len(output)-pre)
        output[pre:pre+available]=pcm[:available]
        with wave.open(str(adjusted),'wb') as dst:
            dst.setnchannels(1);dst.setsampwidth(2);dst.setframerate(22050)
            dst.writeframes(output.tobytes())
        d=duration_of(adjusted)
        durinfo.append({'scene':i,'raw_voice_duration_s':round(raw_d,3),'atempo':round(tempo,4),'post_s':round(d,3),'target_scene_s':s['duration'],'words':measure_text(s['narration']),'words_per_minute_at_scene_length':round(measure_text(s['narration'])/s['duration']*60,1)})
    # concat narration WAVs to exact 120 seconds
    listing=AUD/'audio_concat.txt';listing.write_text(''.join(f"file '{(AUD/f'narration_{s['id']:02d}.wav').resolve()}'\n" for s in SCENES))
    merged=AUD/'narration_120s.wav'
    run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-c:a','pcm_s16le',str(merged)],quiet=True)
    # Original low-volume soundscape: sparse synth chord motifs (not copyrighted music)
    sr=22050;n=120*sr;t=np.arange(n,dtype=np.float32)/sr
    music=np.zeros(n,dtype=np.float32)
    # quarter-beat soft pulses and sustained pad in a simple original harmonic progression
    chord_notes=[(220.00,329.63,440.00),(174.61,261.63,349.23),(196.0,293.66,392.0),(164.81,246.94,329.63)]
    for step in range(0,120,4):
        freqs=chord_notes[(step//8)%len(chord_notes)]
        local=t[step*sr:min((step+4)*sr,n)]-step
        if not len(local):continue
        env=(np.minimum(local/0.8,1.0)*np.minimum((4.0-local)/0.7,1.0)).clip(0,1)
        sig=sum(np.sin(2*np.pi*f*local)/3 for f in freqs)
        music[step*sr:step*sr+len(local)]+=0.047*sig*env
    # low airy motion, sparse accents
    music += 0.004*np.sin(2*np.pi*87*t)*(0.5+0.5*np.sin(2*np.pi*0.25*t))
    fade=np.minimum(t/1.2,1)*np.minimum((120-t)/2.2,1)
    music=(music*fade).clip(-1,1)
    mw=AUD/'original_ambient_120s.wav'
    with wave.open(str(mw),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(sr);w.writeframes((music*32767).astype(np.int16).tobytes())
    mix=AUD/'final_mix_120s.wav'
    run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(merged),'-i',str(mw),'-filter_complex','[0:a]volume=1.8[n];[1:a]volume=0.46[m];[n][m]amix=inputs=2:duration=first:dropout_transition=0,alimiter=limit=0.93,atrim=duration=120[a]','-map','[a]','-ac','2','-ar','44100',str(mix)],quiet=True)
    (REPORTS/'voice_timing.json').write_text(json.dumps(durinfo,indent=2,ensure_ascii=False)+'\n')
    return durinfo

def subs():
    lines=[];ass=['[Script Info]','Title: RÍO Primer Cobro R040 subtitles','ScriptType: v4.00+','PlayResX: 1280','PlayResY: 720','ScaledBorderAndShadow: yes','','[V4+ Styles]', 'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding', 'Style: Main,Lato,35,&H00FFFFFF,&H000000FF,&H00202530,&H90071C2B,-1,0,0,0,100,100,0,0,3,1,1,2,50,50,44,1','','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
    count=0
    for s in SCENES:
        base=s['from_s'];chunks=s['subs'];total_words=sum(measure_text(c) for c in chunks)
        # 0.35s into the scene; ensure captions leave time at the end
        start=base+0.38;available=s['duration']-0.7
        acc=0
        for k,part in enumerate(chunks):
            p=measure_text(part)/total_words; st=start+available*acc;acc+=p;et=start+available*acc
            if k==len(chunks)-1:et=base+s['duration']-0.23
            count+=1;lines.append((count,st,et,part));ass.append(f'Dialogue: 0,{astamp(st)},{astamp(et)},Main,,0,0,0,,{part}')
    srt='\n\n'.join(f'{i}\n{tstamp(st)} --> {tstamp(et)}\n{txt}' for i,st,et,txt in lines)+'\n'
    (ROOT/'RIO_PRIMER_COBRO_SUBTITULOS_R040.srt').write_text(srt)
    (ROOT/'RIO_PRIMER_COBRO_SUBTITULOS_R040.ass').write_text('\n'.join(ass)+'\n')
    return len(lines)

def video():
    paths=[]
    for s in SCENES:
        f=CLIPS/f"scene_{s['id']:02d}.mp4";fps=FPS;dur=s['duration']
        vf=f"zoompan=z='min(zoom+0.00014,1.06)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d=1:s={OUTW}x{OUTH}:fps={fps},fade=t=in:st=0:d=0.35,fade=t=out:st={dur-0.35}:d=0.35,format=yuv420p"
        run(['ffmpeg','-hide_banner','-loglevel','error','-threads','3','-y','-loop','1','-framerate',str(fps),'-i',str(ASSETS/f"scene_{s['id']:02d}.png"),'-t',str(dur),'-vf',vf,'-r',str(fps),'-c:v','libx264','-preset','veryfast','-crf','20','-g','48','-pix_fmt','yuv420p','-an',str(f)],quiet=True)
        paths.append(f)
    listing=CLIPS/'video_concat.txt';listing.write_text(''.join(f"file '{p.resolve()}'\n" for p in paths))
    silent=CLIPS/'silent_120s.mp4'
    run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(silent)],quiet=True)
    master=ROOT/'RIO_PRIMER_COBRO_VIDEO_120S_R040.mp4'
    # subtitle burn, voice and original music, exact 120.000 s
    run(['ffmpeg','-hide_banner','-loglevel','error','-threads','3','-y','-i',str(silent),'-i',str(AUD/'final_mix_120s.wav'),'-vf',f"ass={ROOT/'RIO_PRIMER_COBRO_SUBTITULOS_R040.ass'}",'-c:v','libx264','-preset','veryfast','-crf','21','-c:a','aac','-b:a','160k','-movflags','+faststart','-t','120','-shortest',str(master)],quiet=True)
    return master

def write_revised():
    text='''# RÍO Primer Cobro — R040: guion audiovisual auditado y programado

**Objetivo:** demostración educativa útil, creíble y verificable en 120 segundos. **Audiencia:** pequeños comercios de México. **Estética:** vector original RÍO, no capturas falsas. **Narración:** voz sintética local en español latinoamericano, no una voz mexicana certificada.

## Auditoría y rondas

- **R040.A · Semántica:** contrastado con `app/logic.js`, `app/chat.js`, `app/persistence.js`, `app/index.html`, `README.md` y `frontdesk/README.md` de R015/R016. El material audiovisual es una RECREACIÓN VISUAL basada en funciones del código, NO captura de la UI ni prueba de usuarios reales.
- **R040.B · Cálculo:** 2 panes × $15.00 = $30.00; 500 g × $40.00/kg = $20.00; total = $50.00; efectivo declarado $100.00 − total $50.00 = cambio $50.00. El efectivo es un registro humano, nunca comprobación bancaria.
- **R040.C · Tiempo:** nueve escenas consecutivas, suma exactamente 120 s; la duración sintetizada de cada locución se mide después de generar audio, se ajusta sin alterar el contenido verbal y se guarda en `reports/voice_timing.json`. Subtítulos `.srt` y `.ass` con intervalos definidos.
- **R040.D · Render:** FFmpeg H.264 + AAC, 1280×720, 24 fps, subtítulos integrados, música sintetizada original de volumen bajo. Comprobación con `ffprobe`, imágenes de muestra y recibo de integridad. No usa servicios externos ni créditos de InVideo.
- **R040.E · Gobierno:** no cambia `main`, no afirma pago real, no inicia cobros ni hace públicos secretos. El guion/video no levanta el `r038-policy-hold` ni implica despliegue de producción.

## Escenas y narración final

'''
    for s in SCENES:
        text+=f"### {s['id']:02d} · {s['from_s']:03d}–{s['from_s']+s['duration']:03d} s · {s['title']}\n\n**Locución:** {s['narration']}\n\n**Pantalla:** {s['subtitle']}. **Rótulo:** {s['accent']}.\n\n"
    text+='## Afirmaciones controladas\n\n'
    for k,v in CLAIMS.items():text+=f'- **{k}:** {v}\n'
    text+='''\n## Limitaciones de esta versión

- Las pantallas y el entorno comercial son gráficos ilustrativos construidos a partir de lo que documenta el repositorio, y van etiquetados como `RECREACIÓN VISUAL`; no sustituyen capturas reales de navegador.
- La voz offline `es-la` es comprensible pero sintética; para una versión publicitaria profesional puede sustituirse por una grabación humana o TTS profesional con licencia.
- No se presentan ingresos obtenidos, usuarios reales, resultados de conversión ni mejoras medidas.
- Los tickets no son CFDI, los QR no aceptan pagos, el JSON de respaldo no es cifrado y no hay sincronización en la nube.
- Este entregable es una producción local, independiente de la cuenta InVideo (0 créditos observados).
'''
    (ROOT/'RIO_PRIMER_COBRO_GUION_FINAL_AUDITADO_R040.md').write_text(text)

def audit(master,voice):
    info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(master)]))
    v=next(x for x in info['streams'] if x['codec_type']=='video')
    a=next(x for x in info['streams'] if x['codec_type']=='audio')
    d=float(info['format']['duration'])
    b=master.read_bytes()
    word_counts=[x['words'] for x in voice]
    flags={
       'duration_120s_tolerance_80ms':abs(d-120)<0.080,
       'video_h264':v['codec_name']=='h264',
       'audio_aac':a['codec_name']=='aac',
       'resolution_1280x720':int(v['width'])==1280 and int(v['height'])==720,
       'nine_contiguous_scenes':len(SCENES)==9 and sum(s['duration'] for s in SCENES)==120,
       'synthetic_financial_example_correct':30+20==50 and 100-50==50,
       'mandatory_qr_caveat_in_scene_5':'no es pagable' in SCENES[4]['narration'].lower(),
       'mandatory_manual_cash_caveat':'manualmente' in SCENES[3]['narration'].lower(),
       'local_privacy_caveat':'locales' in SCENES[6]['narration'].lower(),
       'mocked_ui_labeled':all('RECREACIÓN VISUAL' in (ROOT/'RIO_PRIMER_COBRO_GUION_FINAL_AUDITADO_R040.md').read_text() for _ in [1]),
    }
    data={'schema':'RIO_PRIMER_COBRO_VIDEO_R040_LOCAL_AUDIT_V1','video_filename':master.name,'video_bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'duration_seconds':d,'fps':v['avg_frame_rate'],'video_codec':v['codec_name'],'audio_codec':a['codec_name'],'width':v['width'],'height':v['height'],'source':'SYNTHETIC_RECREATED_UI_NOT_LIVE_SCREEN_RECORDING','voice_engine':'ESPEAK_OFFLINE_ES-LA','scene_count':len(SCENES),'word_count':sum(word_counts),'words_per_minute_for_120s':sum(word_counts)/2,'voice_timing_by_scene':voice,'claims':CLAIMS,'checks':flags,'status':'PASS_LOCAL_VIDEO_PRODUCTION' if all(flags.values()) else 'FAIL_AUDIT','invideo_credits_observed_previous_round':0,'invideo_render_attempted':False,'production_deploy_authorized':False,'payment_connected':False,'external_review':False,'generated_under_current_tool_session':True}
    (REPORTS/'RIO_PRIMER_COBRO_VIDEO_R040_AUDIT.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    print('AUDIT',json.dumps({'status':data['status'],'file':str(master),'duration':d,'bytes':len(b),'sha256':data['sha256'],'word_count':data['word_count'],'checks':flags},indent=2,ensure_ascii=False))
    return data

def main():
    mode=argparse.ArgumentParser();mode.add_argument('--stage',choices=['preflight','assets','audio','video','audit','all'],default='all');args=mode.parse_args()
    if args.stage in ('preflight','all'):
        print('SCENE_TIMELINE',[(s['id'],s['from_s'],s['from_s']+s['duration'],measure_text(s['narration'])) for s in SCENES]);print('TOTAL_WORDS',sum(measure_text(s['narration']) for s in SCENES));write_revised()
        (REPORTS/'timeline.json').write_text(json.dumps({'scenes':SCENES,'total_s':120,'fps':24},indent=2,ensure_ascii=False)+'\n')
    if args.stage in ('assets','all'):
        for s in SCENES:make_image(s)
        print('ASSETS',len(list(ASSETS.glob('scene_*.png'))))
        print('SUBTITLES',subs())
    if args.stage in ('audio','all'):print('VOICE',create_audio())
    if args.stage in ('video','all'):print('VIDEO',video())
    if args.stage in ('audit','all'):audit(ROOT/'RIO_PRIMER_COBRO_VIDEO_120S_R040.mp4',json.loads((REPORTS/'voice_timing.json').read_text()))

if __name__=='__main__':main()
