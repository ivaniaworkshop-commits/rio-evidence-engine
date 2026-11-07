#!/usr/bin/env python3
"""RÍO R041: investor-facing commercial thesis video (not a product tutorial).
Original deterministic vector frames, offline espeak narration, generated music.
All metrics are explicitly hypothetical; no payment, investment, or real-user data.
"""
import os,sys,re,json,math,hashlib,wave,subprocess,shutil,random
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
import numpy as np

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'assets';CLIPS=ROOT/'clips';AUDIO=ROOT/'audio';REPORTS=ROOT/'reports'
for d in [ASSETS,CLIPS,AUDIO,REPORTS]: d.mkdir(exist_ok=True)
SCENES=[
 dict(d=12,kicker='TESIS DE INVERSIÓN',title='Del primer cobro al ecosistema',sub='Una puerta de entrada para el pequeño comercio',kind='hero',n='¿Y si el primer cobro también fuera el primer paso de una plataforma comercial? RÍO quiere acompañar a pequeños negocios desde una tarea cotidiana.',capt=['¿Y si el primer cobro fuera el inicio de una plataforma comercial?','RÍO: una puerta de entrada para el pequeño comercio.']),
 dict(d=13,kicker='01  /  EL PROBLEMA',title='El reto va más allá de cobrar',sub='Procesos aislados frenan la continuidad del negocio',kind='problem',n='Muchos comercios combinan papel, calculadora y herramientas aisladas. El reto no es solamente cobrar: es transformar la actividad diaria en organización, aprendizaje y nuevas oportunidades.',capt=['Muchos comercios usan herramientas aisladas.','La oportunidad: conectar operación, información y crecimiento.']),
 dict(d=13,kicker='02  /  LO QUE YA EXISTE',title='Una primera puerta funcional',sub='RÍO Primer Cobro · demo educativa R015/R016',kind='product',n='La primera pieza existe: RÍO Primer Cobro. Una caja educativa gratuita con cálculo por pieza o peso, efectivo declarado, tickets, historial y un QR de práctica que no recibe dinero.',capt=['Ya existe una caja educativa gratuita.','Piezas, peso, efectivo declarado, tickets e historial.']),
 dict(d=13,kicker='03  /  HIPÓTESIS DE DISTRIBUCIÓN',title='Empezar gratis. Medir el valor.',sub='Propuesta de captación de baja fricción, aún sin validación de mercado',kind='funnel',n='Nuestra tesis de distribución empieza por ayudar gratis. Después medimos uso repetido, confianza y necesidades. La adquisición de comercios es todavía una hipótesis; no estamos reportando clientes activos.',capt=['Nuestra tesis: ayudar primero y medir la recurrencia.','La adquisición de comercios todavía debe validarse.']),
 dict(d=15,kicker='04  /  HOJA DE RUTA',title='Una escalera de servicios',sub='De práctica educativa a herramientas comerciales integradas',kind='roadmap',n='La evolución propuesta suma punto de venta, inventario, CRM y cotizaciones. Después podría conectar minoristas, mayoristas y logística. Son módulos e integraciones por construir o validar; no servicios productivos de Primer Cobro.',capt=['Propuesta: punto de venta, inventario, CRM y cotizaciones.','Más adelante: mayoristas y logística, sujetos a validación.']),
 dict(d=14,kicker='05  /  MODELO COMERCIAL',title='Monetización por capas',sub='Acceso gratuito + servicios de valor agregado',kind='revenue',n='El modelo potencial tiene tres capas: educación gratuita, suscripciones a herramientas profesionales y comisiones por servicios transaccionales. Precios, adopción, costos y márgenes requieren pruebas antes de invertir a escala.',capt=['Educación gratuita, suscripción y comisión: modelo propuesto.','Precio, adopción y margen todavía deben comprobarse.']),
 dict(d=18,kicker='06  /  SENSIBILIDAD FINANCIERA',title='El modelo se puede calcular',sub='Escenario matemático ilustrativo · no pronóstico',kind='math',n='Un escenario hipotético: diez mil comercios activos, cinco por ciento de conversión y una suscripción supuesta de noventa y nueve pesos mensuales. El resultado sería cuarenta y nueve mil quinientos pesos mensuales brutos, antes de costos. No es ingreso observado ni una proyección.',capt=['Escenario hipotético: diez mil comercios; cinco por ciento convierte.','A noventa y nueve pesos: cuarenta y nueve mil quinientos mensuales brutos.','No es ingreso real ni pronóstico.']),
 dict(d=11,kicker='07  /  DESRIESGO',title='La evidencia marca los hitos',sub='El siguiente objetivo es validar economía y adopción',kind='risk',n='Hoy hay software y pruebas técnicas. Faltan pilotos con comerciantes, retención, costo de adquisición, conversión y autorizaciones de producción.',capt=['Software y pruebas: evidencia disponible.','Retención, CAC y conversión: pendientes de medir.']),
 dict(d=11,kicker='08  /  INVITACIÓN',title='Validemos el potencial juntos',sub='Pilotos comerciales, métricas claras, decisiones por evidencia',kind='close',n='Buscamos aliados para pilotos medibles en México. Validemos adopción, ingresos por comercio y costos. RÍO: del primer cobro a una red comercial conectada.',capt=['Buscamos aliados para pilotos medibles en México.','RÍO: del primer cobro a una red comercial conectada.'])
]
assert sum(s['d'] for s in SCENES)==120
T=0
for i,s in enumerate(SCENES):s.update(index=i+1,start=T,end=T+s['d']);T+=s['d']
GOLD='#FFCC83';AQUA='#65E3C9';WHITE='#F5FCFD';MUTED='#B1CCD6';BG='#071E30';BG2='#0C3344';SKY='#1A6173';INK='#0A2432';DANGER='#E7A56C';LILAC='#D4C6FF'
FONTS={'heavy':'/usr/share/fonts/truetype/lato/Lato-Heavy.ttf','bold':'/usr/share/fonts/truetype/lato/Lato-Bold.ttf','reg':'/usr/share/fonts/truetype/lato/Lato-Regular.ttf','medium':'/usr/share/fonts/truetype/lato/Lato-Medium.ttf'}
FNT={}
def font(size,kind='reg'):
 key=(size,kind)
 if key not in FNT:FNT[key]=ImageFont.truetype(FONTS.get(kind,FONTS['reg']),size)
 return FNT[key]
def say(d,xy,text,size=40,color=WHITE,weight='reg',anchor=None):
 d.text(xy,text,fill=color,font=font(size,weight),anchor=anchor)
def rounded(d,box,fill,r=22,outline=None,width=2):d.rounded_rectangle(tuple(map(int,box)),radius=r,fill=fill,outline=outline,width=width)
def lines(text,width,size=50,kind='bold'):
 out=[];p=''
 for w in text.split():
  t=(p+' '+w).strip()
  if font(size,kind).getlength(t)>width and p:out.append(p);p=w
  else:p=t
 if p:out.append(p)
 return out
def block(d,text,x,y,w,size=47,color=WHITE,weight='bold',spacing=1.18,maxlines=4):
 for j,line in enumerate(lines(text,w,size,weight)[:maxlines]):say(d,(x,y+int(size*spacing)*j),line,size,color,weight)
def tag(d,text,x,y,color=AQUA,sz=21):say(d,(x,y),text,sz,color,'heavy')
def pill(d,label,box,fill='#144D5D',color=WHITE,fs=25):
 rounded(d,box,fill,r=18); say(d,((box[0]+box[2])/2,(box[1]+box[3])/2),label,fs,color,'bold',anchor='mm')
def base(w,h,i,portrait=False):
 yy,xx=np.mgrid[0:h,0:w]
 a=np.clip(.08+.29*(xx/w)+.23*(yy/h),0,.66)
 c1=np.array((5,22,36),float);c2=np.array((16,66,79),float)
 arr=(c1[None,None,:]*(1-a[:,:,None])+c2[None,None,:]*a[:,:,None]).clip(0,255).astype('uint8')
 im=Image.fromarray(arr,'RGB').convert('RGBA');d=ImageDraw.Draw(im)
 d.ellipse((w-490,-270,w+210,420),outline='#1E6776',width=3)
 d.ellipse((w-400,-170,w+140,370),outline='#136073',width=2)
 d.ellipse((-390,h-220,350,h+460),outline='#1A5367',width=2)
 d.line((52,106,w-52,106),fill='#1A5E6D',width=2)
 say(d,(58,45),'RÍO / MERCADO COMERCIAL',24,AQUA,'heavy')
 say(d,(w-59,49),'TESIS · NO OFERTA PÚBLICA',16,MUTED,'bold',anchor='ra')
 for j in range(9):rounded(d,(58+j*42,121,90+j*42,126),AQUA if j==i else '#275463',r=2)
 d.line((55,h-94,w-55,h-94),fill='#2B6171',width=2)
 say(d,(58,h-75),'INVERSIONISTAS   /   RÍO PRIMER COBRO',18,MUTED,'bold')
 say(d,(w-62,h-75),f'{i+1:02d}/09   ·   ESCENARIO INFORMATIVO',17,MUTED,'bold',anchor='ra')
 return im,d

def draw_store(d,x,y):
 rounded(d,(x,y+65,x+240,y+225),'#E6F1EF',r=13)
 d.polygon([(x-15,y+77),(x+24,y+12),(x+210,y+12),(x+255,y+77)],fill=GOLD)
 for j in range(5):d.rectangle((x+j*48,y+77,x+(j+1)*48,y+109),fill='#E58F70' if j%2 else '#FFDC9E')
 rounded(d,(x+24,y+118,x+215,y+190),'#207688',r=5)
 for j,c in enumerate(['#ED8C68','#C0BD5B','#ED8C68','#9ECA81']):d.ellipse((x+33+j*44,y+132,x+65+j*44,y+164),fill=c)
 say(d,(x+120,y+207),'COMERCIO',16,'#1A6273','heavy',anchor='mm')

def content_h(d,s):
 k=s['kind'];right=(750,205,1500,735)
 if k=='hero':
  # merchant to connected system thesis
  rounded(d,(785,205,1458,694),'#0C3548',r=40,outline='#267B84')
  draw_store(d,815,293)
  say(d,(1095,376),'→',80,AQUA,'heavy')
  for j,(a,b) in enumerate([('VENTAS','BASE'),('OPERACIÓN','SERVICIO'),('RED','COMERCIAL')]):
   x=1215;y=253+j*119
   rounded(d,(x,y,x+205,y+96),'#165467',r=18,outline='#2E8490')
   say(d,(x+103,y+36),a,21,WHITE,'heavy',anchor='mm')
   say(d,(x+103,y+65),b,17,AQUA,'bold',anchor='mm')
  say(d,(990,623),'PRÁCTICA → RELACIÓN → VALOR',24,GOLD,'heavy')
 elif k=='problem':
  labels=[('1','OPERACIÓN EN PAPEL'),('2','HERRAMIENTAS SUELTAS'),('3','DATOS FRAGMENTADOS')]
  for j,(num,v) in enumerate(labels):
   y=248+j*146;rounded(d,(800,y,1457,y+106),'#16495B',r=18,outline='#2B6A7A');pill(d,num,(822,y+24,886,y+85),'#285D6B',GOLD,27);say(d,(920,y+45),v,25,WHITE,'heavy')
  say(d,(830,713),'HIPÓTESIS DE DOLOR · REQUIERE ENTREVISTAS',19,GOLD,'bold')
 elif k=='product':
  rounded(d,(815,203,1440,696),'#EAF4F3',r=35)
  rounded(d,(838,226,1415,294),'#0F5E6C',r=14);say(d,(865,248),'RÍO · PRIMER COBRO',29,WHITE,'heavy')
  for j,t in enumerate(['PIEZAS Y PESO','EFECTIVO DECLARADO','TICKET E HISTORIAL','AYUDA LOCAL','QR NO PAGABLE']):
   y=319+j*65;rounded(d,(852,y,1398,y+51),'#D5EAE8',r=9);say(d,(875,y+11),'✓',29,'#0C826B','bold');say(d,(922,y+14),t,24,'#164C5C','heavy')
  say(d,(1105,674),'DEMO DOCUMENTADA EN CÓDIGO',17,'#1B6879','heavy',anchor='mm')
 elif k=='funnel':
  steps=[('01','ENTRADA GRATIS','PROTOTIPO EXISTENTE'),('02','USO RECURRENTE','MÉTRICA NO OBSERVADA'),('03','CONVERSIÓN','POR VALIDAR')]
  for j,(num,name,status) in enumerate(steps):
   y=217+j*154;ww=660-j*112;x=824+j*56
   rounded(d,(x,y,x+ww,y+113),['#155C67','#136070','#185062'][j],r=20,outline='#308B91')
   pill(d,num,(x+20,y+23,x+83,y+78),'#227686',GOLD,23)
   say(d,(x+106,y+24),name,28,WHITE,'heavy');say(d,(x+106,y+73),status,16,GOLD,'heavy')
  say(d,(840,705),'FUNNEL CONCEPTUAL · SIN CLIENTES CONTABILIZADOS',18,MUTED,'bold')
 elif k=='roadmap':
  nodes=[('HOY','CAJA EDUCATIVA','OPERATIVA EN DEMO'),('SIGUIENTE','POS · CRM · INVENTARIO','PLAN / DESARROLLO'),('DESPUÉS','RFQ · FLETES · RED','INTEGRACIÓN FUTURA')]
  for j,(phase,product,status) in enumerate(nodes):
   y=222+j*152;rounded(d,(809,y,1464,y+112),'#135265',r=20,outline='#257E88')
   say(d,(837,y+19),phase,18,GOLD,'heavy');say(d,(837,y+48),product,28,WHITE,'heavy');say(d,(837,y+85),status,16,AQUA if j==0 else '#CFD7E8','bold')
   if j<2:say(d,(1480,y+102),'↓',28,AQUA,'bold',anchor='ra')
 elif k=='revenue':
  products=[('GRATIS','ENTRADA','OPERATIVA'),('SUSCRIPCIÓN','SOFTWARE','HIPÓTESIS'),('COMISIÓN','SERVICIOS','HIPÓTESIS')]
  for j,(a,b,c) in enumerate(products):
   x=777+j*236
   rounded(d,(x,250,x+218,618),'#154A5A',r=24,outline='#2C7C88')
   rounded(d,(x+18,269,x+200,332),['#1D8B82','#275F80','#775878'][j],r=12)
   say(d,(x+109,302),a,22,WHITE,'heavy',anchor='mm')
   say(d,(x+109,399),b,25,WHITE,'heavy',anchor='mm')
   say(d,(x+109,540),c,19,GOLD,'heavy',anchor='mm')
  say(d,(824,688),'UNIT ECONOMICS: COSTOS / MARGEN / CAC = POR MEDIR',19,MUTED,'heavy')
 elif k=='math':
  rounded(d,(802,207,1488,655),'#F2F9F7',r=35)
  say(d,(837,236),'ESCENARIO HIPOTÉTICO',22,'#075B67','heavy')
  labs=[('10,000','COMERCIOS'),('5%','CONVERSIÓN'),('$99','MXN / MES')]
  for j,(a,b) in enumerate(labs):
   x=817+j*223
   say(d,(x+108,338),a,47,'#145870','heavy',anchor='mm')
   say(d,(x+108,394),b,17,'#396978','heavy',anchor='mm')
   if j<2:say(d,(x+218,369),'×',30,'#B27A33','heavy',anchor='mm')
  rounded(d,(831,441,1463,566),'#125E6D',r=20)
  say(d,(1145,482),'$49,500 MXN / MES',43,WHITE,'heavy',anchor='mm')
  say(d,(1145,539),'INGRESO BRUTO SIMULADO',17,GOLD,'heavy',anchor='mm')
  say(d,(1145,616),'ANTES DE COSTOS · NO INGRESO REAL',19,'#A4492B','heavy',anchor='mm')
 elif k=='risk':
  rounded(d,(801,236,1450,365),'#145568',r=20)
  say(d,(830,256),'OBSERVADO',20,AQUA,'heavy');say(d,(830,306),'Código de demo + pruebas técnicas',29,WHITE,'heavy')
  rounded(d,(801,397,1450,603),'#384B64',r=20)
  say(d,(830,415),'PENDIENTE DE VALIDAR',21,GOLD,'heavy')
  block(d,'Pilotos · retención · CAC · conversión · permisos',830,468,590,26,WHITE,'bold',1.33)
  say(d,(815,683),'RESULTADO TÉCNICO ≠ TRACCIÓN COMERCIAL',22,GOLD,'heavy')
 elif k=='close':
  rounded(d,(810,222,1460,654),'#103D50',r=34,outline='#24848D')
  for j,t in enumerate(['PILOTOS REALES','RETENCIÓN Y VALOR','ECONOMÍA POR COMERCIO']):
   y=273+j*108;rounded(d,(842,y,1431,y+79),'#175766',r=12)
   say(d,(868,y+22),['01','02','03'][j],27,GOLD,'heavy');say(d,(939,y+24),t,25,WHITE,'heavy')
  say(d,(1135,704),'ALIANZAS PARA VALIDAR EN MÉXICO',22,AQUA,'heavy',anchor='mm')

def make_horizontal(s):
 im,d=base(1600,900,s['index']-1)
 tag(d,s['kicker'],62,172,GOLD,24)
 title_size=67 if len(s['title'])<29 else 61
 block(d,s['title'],62,246,700,title_size,WHITE,'heavy',1.13,3)
 yy=420 if len(lines(s['title'],700,title_size,'heavy'))>1 else 342
 block(d,s['sub'],65,yy,663,32,MUTED,'medium',1.32,4)
 # Investor thesis evidence discipline footer, constant on each slide
 rounded(d,(61,615,710,708),'#124658',r=22,outline='#297787')
 tag(d,'DECISIÓN POR EVIDENCIA',93,635,AQUA,26)
 say(d,(94,678),'PROTOTIPO ≠ CRECIMIENTO DEMOSTRADO',17,WHITE,'bold')
 content_h(d,s)
 im.convert('RGB').save(ASSETS/f'h_{s["index"]:02d}.png',optimize=True)

def portrait_content(d,s):
 k=s['kind']
 # Fit narrower visual space on portrait with bespoke features
 if k in ('hero','problem'):
  for j,t in enumerate(['COMERCIO LOCAL','OPERACIÓN DIGITAL','RED COMERCIAL']):
   y=746+j*135;rounded(d,(80,y,820,y+108),'#175367',r=24,outline='#29818A')
   say(d,(124,y+35),['01','02','03'][j],28,GOLD,'heavy');say(d,(216,y+38),t,29,WHITE,'heavy')
 elif k=='product':
  for j,t in enumerate(['CÁLCULO POR PIEZA Y PESO','EFECTIVO DECLARADO','TICKET + HISTORIAL','QR EDUCATIVO · NO PAGABLE']):
   y=734+j*121;rounded(d,(79,y,824,y+93),'#DCEDEA',r=18)
   say(d,(111,y+29),'✓',29,'#0B795F','heavy');say(d,(166,y+29),t,27,'#145063','heavy')
 elif k=='funnel':
  for j,(a,b) in enumerate([('ENTRADA GRATIS','DEMO DISPONIBLE'),('USO REPETIDO','POR MEDIR'),('CONVERSIÓN','POR VALIDAR')]):
   y=750+j*151;rounded(d,(88+j*30,y,816-j*30,y+117),'#176071',r=18)
   say(d,(130+j*30,y+30),a,30,WHITE,'heavy');say(d,(130+j*30,y+75),b,21,GOLD,'heavy')
 elif k=='roadmap':
  for j,(a,b,c) in enumerate([('HOY','CAJA EDUCATIVA','CÓDIGO REAL'),('SIGUIENTE','POS + INVENTARIO + CRM','PROPUESTA'),('POSTERIOR','MAYOREO + LOGÍSTICA','POR VALIDAR')]):
   y=724+j*151;rounded(d,(78,y,823,y+117),'#155466',r=18)
   say(d,(115,y+15),a,20,GOLD,'heavy');say(d,(115,y+50),b,29,WHITE,'heavy');say(d,(115,y+88),c,18,AQUA,'bold')
 elif k=='revenue':
  for j,(a,b) in enumerate([('ENTRADA GRATUITA','EN DEMO'),('SUSCRIPCIÓN','HIPÓTESIS'),('COMISIONES','HIPÓTESIS')]):
   y=722+j*157;rounded(d,(80,y,820,y+119),'#185466',r=20)
   say(d,(113,y+21),a,34,WHITE,'heavy');say(d,(114,y+77),b,22,GOLD,'heavy')
 elif k=='math':
  rounded(d,(78,730,823,1220),'#F2F9F7',r=28)
  say(d,(116,752),'SUPUESTOS HIPOTÉTICOS',22,'#136179','heavy')
  for j,t in enumerate(['10,000 comercios activos','× 5% de conversión','× $99 MXN / mes']):say(d,(129,813+j*73),t,35,'#145269','heavy')
  rounded(d,(110,1068,795,1178),'#0C6274',r=16)
  say(d,(452,1114),'$49,500 / MES',47,WHITE,'heavy',anchor='mm')
  say(d,(450,1239),'INGRESO BRUTO SIMULADO · NO PRONÓSTICO',20,GOLD,'bold',anchor='mm')
 elif k=='risk':
  rounded(d,(75,770,821,925),'#12546A',r=20)
  tag(d,'HECHO',107,796,AQUA,22);say(d,(107,850),'Software + pruebas técnicas',32,WHITE,'heavy')
  rounded(d,(75,959,821,1190),'#4A5165',r=20)
  tag(d,'NO OBSERVADO',107,984,GOLD,22)
  block(d,'Pilotos, retención, CAC, conversión y producción',107,1032,655,31,WHITE,'bold',1.2)
 elif k=='close':
  for j,t in enumerate(['PILOTOS MEDIBLES','CONVERSIÓN VALIDADA','COSTOS OBSERVADOS']):
   y=736+j*148;rounded(d,(85,y,821,y+108),'#14596A',r=22,outline='#287783');say(d,(121,y+35),f'{j+1:02d}',30,GOLD,'heavy');say(d,(211,y+36),t,32,WHITE,'heavy')

def make_vertical(s):
 im,d=base(900,1600,s['index']-1,True)
 tag(d,s['kicker'],65,197,GOLD,23)
 ts=72 if len(s['title'])<30 else 63
 block(d,s['title'],67,287,762,ts,WHITE,'heavy',1.14,4)
 head_lines=len(lines(s['title'],762,ts,'heavy'))
 sy=287+head_lines*int(ts*1.14)+26
 block(d,s['sub'],69,sy,753,34,MUTED,'medium',1.25,4)
 # clear divider at 675
 d.line((80,692,820,692),fill='#24667A',width=3)
 portrait_content(d,s)
 say(d,(91,1342),'RÍO · TESIS COMERCIAL',27,AQUA,'heavy')
 say(d,(91,1396),'REAL ≠ HIPÓTESIS',25,GOLD,'heavy')
 im.convert('RGB').save(ASSETS/f'v_{s["index"]:02d}.png',optimize=True)

def timestamp(t,ass=False):
 t=round(float(t),2 if ass else 3)
 hh=int(t//3600);mm=int(t%3600//60);ss=int(t%60)
 cs=int(round((t-int(t))* (100 if ass else 1000)))
 if ass:return f'{hh}:{mm:02d}:{ss:02d}.{cs:02d}'
 return f'{hh:02d}:{mm:02d}:{ss:02d},{cs:03d}'

def subtitle_files():
 # 9 scenes, each split by 2/3 subphrase, bounded by scene
 cues=[]
 for s in SCENES:
  ss=s['capt'];total=sum(len(x.split()) for x in ss);a=s['start']+.5
  for t in ss:
   frac=len(t.split())/total
   b=a+(s['d']-1)*frac
   cues.append((a,b,t));a=b
   if t is ss[-1]:a=s['end']
 st='\n\n'.join(f'{i}\n{timestamp(a)} --> {timestamp(b)}\n{t}' for i,(a,b,t) in enumerate(cues,1))+'\n'
 (ROOT/'R041_SUBTITULOS_ES_MX.srt').write_text(st)
 for orientation,(xx,yy,sz,mv) in {'h':(1280,720,34,34),'v':(720,1280,28,54)}.items():
  a=['[Script Info]','Title: RIO R041 Investor subtitles','ScriptType: v4.00+','PlayResX: '+str(xx),'PlayResY: '+str(yy),'ScaledBorderAndShadow: yes','','[V4+ Styles]','Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',f'Style: Main,Lato,{sz},&H00FFFFFF,&H000000FF,&H00202A31,&HA500111F,-1,0,0,0,100,100,0,0,3,1,1,2,42,42,{mv},1','','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text']
  for begin,end,line in cues:a.append(f'Dialogue: 0,{timestamp(begin,True)},{timestamp(end,True)},Main,,0,0,0,,{line}')
  (ROOT/f'R041_SUBTITULOS_{orientation}.ass').write_text('\n'.join(a)+'\n')
 return cues

def execute(cmd):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 if p.returncode!=0:raise RuntimeError('EXIT '+str(p.returncode)+'\n'+p.stderr[-3000:]+'\n'+' '.join(map(str,cmd)))
 return p

def dur(path):return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)]))

def audio_master():
 info=[];files=[];sample=22050
 for s in SCENES:
  f=AUDIO/f'raw_{s["index"]:02d}.wav';execute(['espeak','-v','es-la','-s','195','-p','47','-a','175','-w',str(f),s['n']])
  original=dur(f);max_voice=s['d']-1.05
  stretch=max(original/max_voice,0.93) if original>max_voice else 1.0
  # atempo: faster if raw too long; rarely changes speed more than 18%
  final=AUDIO/f'voice_{s["index"]:02d}.wav'
  filter=f'aresample=22050,highpass=f=85,lowpass=f=7900,atempo={stretch:.5f},adelay=280|280,apad=whole_dur={s["d"]},atrim=duration={s["d"]},asetpts=PTS-STARTPTS'
  execute(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(f),'-af',filter,'-ar','22050','-ac','1',str(final)])
  fixed=AUDIO/f'voice_fixed_{s["index"]:02d}.wav'
  execute(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(final),'-af',f'apad=whole_dur={s["d"]},atrim=duration={s["d"]}','-ar','22050','-ac','1',str(fixed)])
  assert abs(dur(fixed)-s['d'])<0.002,(s['index'],dur(fixed))
  info.append(dict(scene=s['index'],budget_seconds=s['d'],raw_voice_seconds=original,tempo=stretch,padded_duration_seconds=dur(fixed),spoken_words=len(s['n'].split())))
  files.append(fixed)
 p=AUDIO/'voice_concat.txt';p.write_text(''.join(f"file '{x.resolve()}'\n" for x in files))
 narration=AUDIO/'narration_120s.wav';execute(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(p),'-ar','44100','-ac','2',str(narration)])
 # Original non-copyrighted sparse corporate ambient; no prior audio used
 sr=22050;tt=np.arange(120*sr,dtype=np.float32)/sr;music=np.zeros_like(tt)
 notes=[110.0,164.81,196.0,246.94]
 for j,root in enumerate(notes):
  env=0.55+0.40*np.sin(2*np.pi*tt/(23+j*7)+j)
  music+=(0.014+0.005*j)*np.sin(2*np.pi*root*tt+j*.9)*env
 music+=0.006*np.sin(2*np.pi*55*tt)*(np.sin(2*np.pi*1.13*tt)>0.65)
 # light soft percussive pulses; no copyrighted melody
 for beat in np.arange(.5,120,60/94):
  start=int(beat*sr);length=min(int(.14*sr),len(music)-start)
  if length>0:
   lt=np.arange(length)/sr
   music[start:start+length]+=0.033*np.sin(2*np.pi*(130-60*lt)*lt)*np.exp(-22*lt)
 fade=np.minimum(tt/2,1)*np.minimum((120-tt)/2,1)
 pcm=np.int16(np.clip(music*fade,-1,1)*32767)
 musicpath=AUDIO/'original_music.wav'
 with wave.open(str(musicpath),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr);f.writeframes(pcm.tobytes())
 mix=AUDIO/'master_mix_120s.wav'
 execute(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(narration),'-i',str(musicpath),'-filter_complex','[0:a]volume=1.52,acompressor=threshold=-24dB:ratio=2:attack=6:release=130[n];[1:a]volume=0.60[m];[n][m]amix=inputs=2:duration=longest,alimiter=limit=0.95,apad=whole_dur=120,atrim=duration=120[a]','-map','[a]','-ar','44100','-ac','2',str(mix)])
 (REPORTS/'voice_timing.json').write_text(json.dumps(info,ensure_ascii=False,indent=2)+'\n')
 return info

def render(orientation):
 w,h=(1280,720) if orientation=='h' else (720,1280)
 fps=24; vids=[]
 for s in SCENES:
  path=ASSETS/f'{orientation}_{s["index"]:02d}.png';out=CLIPS/f'{orientation}_{s["index"]:02d}.mp4'
  # Keep previously verified exact-duration clips and avoid redundant render.
  if out.exists():
   try:
    if abs(dur(out)-s['d'])<0.020:
     vids.append(out);continue
   except Exception:pass
  # Efficient static-frame motion graphics with scene fades (works offline on CPU).
  vf=f"scale={w}:{h},fade=t=in:st=0:d=0.30,fade=t=out:st={s['d']-.30}:d=0.30,format=yuv420p"
  execute(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','3','-loop','1','-framerate','24','-i',str(path),'-t',str(s['d']),'-vf',vf,'-r','24','-c:v','libx264','-preset','ultrafast','-crf','21','-pix_fmt','yuv420p','-an',str(out)])
  vids.append(out)
 concat=CLIPS/f'{orientation}_concat.txt';concat.write_text(''.join(f"file '{x.resolve()}'\n" for x in vids))
 silent=CLIPS/f'{orientation}_silent.mp4';execute(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy',str(silent)])
 target=ROOT/('RIO_R041_PITCH_INVERSIONISTAS_120S_HORIZONTAL.mp4' if orientation=='h' else 'RIO_R041_PITCH_INVERSIONISTAS_120S_VERTICAL.mp4')
 ass=ROOT/f'R041_SUBTITULOS_{orientation}.ass'
 # Opaque caption bed masks static scene footer; never cover slide content.
 cap_y=618 if orientation=='h' else 1098
 cap_h=102 if orientation=='h' else 182
 vf_final=f'drawbox=x=0:y={cap_y}:w={w}:h={cap_h}:color=0x071E30:t=fill,drawbox=x=0:y={cap_y}:w={w}:h=2:color=0x256579:t=fill,ass={ass}'
 execute(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','3','-i',str(silent),'-i',str(AUDIO/'master_mix_120s.wav'),'-vf',vf_final, '-c:v','libx264','-preset','veryfast','-crf','21','-c:a','aac','-b:a','160k','-pix_fmt','yuv420p','-movflags','+faststart','-t','120','-shortest',str(target)])
 return target

def do_qa(outputs,cues,voice):
 per={}
 for name,path in outputs.items():
  j=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
  v=next(t for t in j['streams'] if t['codec_type']=='video');a=next(t for t in j['streams'] if t['codec_type']=='audio');d=float(j['format']['duration'])
  per[name]=dict(path=str(path),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),duration=d,video_codec=v['codec_name'],audio_codec=a['codec_name'],width=v['width'],height=v['height'],fps=v['avg_frame_rate'])
  assert abs(d-120)<0.07 and v['codec_name']=='h264' and a['codec_name']=='aac',name
 checks=dict(scene_count=len(SCENES)==9,contiguous=sum(s['d'] for s in SCENES)==120 and all(SCENES[i]['end']==SCENES[i+1]['start'] for i in range(8)),subtitles_bounded=all(0<=a<b<=120 for a,b,_ in cues),captions_dont_cross=all(cues[i][1]<=cues[i+1][0]+.53 for i in range(len(cues)-1)),example_valid=10000*.05*99==49500,financial_disclosure_in_narration='hipotético' in SCENES[6]['n'].lower() and 'no es ingreso observado' in SCENES[6]['n'].lower(),business_validity='hipótesis' in SCENES[3]['n'].lower() and 'falta' in SCENES[7]['n'].lower(),payments_caveat='no recibe dinero' in SCENES[2]['n'].lower(),not_pretend_published=True)
 assert all(checks.values()),checks
 audit=dict(schema='RIO_R041_INVESTOR_VIDEO_LOCAL_QA_V1',audience='investment-partners-not-end-users',result='PASS_LOCAL_AV',source='commercial-narrative-from-verified-R015-R016-plus-explicit-new-hypotheses',portfolio_status='DEMO_ONLY_NOT_INVESTMENT_OFFER',total_seconds=120,spoken_words=sum(len(s['n'].split()) for s in SCENES),hypothetical_scenario={'merchants_active_ASSUMED':10000,'conversion_ASSUMED':.05,'subscription_mxn_month_ASSUMED':99,'gross_monthly_mxn_COMPUTED':49500,'observed_revenue':'NOT_VERIFIED','is_forecast':False},voice='ESPEAK_ES-LA_SYNTHETIC_NOT_HUMAN',metrics={'commercial_adoption':'NOT_OBSERVED','retention':'NOT_OBSERVED','CAC':'NOT_OBSERVED','payment_readiness':'BLOCKED'},files=per,checks=checks,generated_by='LOCAL_FFMPEG_PIL_ESPEAK',invideo_credits_required=0,invideo_render=False)
 (REPORTS/'R041_AUDITORIA_FINAL.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
 return audit

def contact_sheet():
 imgs=[]
 for s in SCENES:
  im=Image.open(ASSETS/f'h_{s["index"]:02d}.png').resize((560,315))
  imgs.append(im)
 sheet=Image.new('RGB',(3*560,3*315),(5,20,30))
 for i,im in enumerate(imgs):sheet.paste(im,((i%3)*560,(i//3)*315))
 p=ROOT/'R041_CONTACT_SHEET.png';sheet.save(p);return p

def write_docs(audit):
 out=['# RÍO — Video para inversionistas (R041)','', '**Tipo:** tesis comercial / oportunidad de validación. **Duración:** 120 segundos. **No es video educativo dirigido a usuarios.**','','## Guion por escenas','']
 for s in SCENES:out.extend([f'### {s["index"]:02d} · {s["start"]:03d}–{s["end"]:03d} s · {s["title"]}','',f'**Narración:** {s["n"]}','','**Visual:** '+s['kicker']+' — '+s['sub'],''])
 out.extend(['## Separación epistemológica','','- **HECHO digital:** demo R015/R016 con venta ficticia, totales, efectivo manual, ticket, historial en navegador y QR no pagable.','- **HIPÓTESIS comercial:** la demo gratuita podría ser una puerta de adquisición para productos POS, CRM, ERP, RFQ y logística. **No están integrados en Primer Cobro productivo.**','- **ESCENARIO DE SENSIBILIDAD, NO PRONÓSTICO:** 10,000 comercios activos supuestos × 5% conversión supuesta × $99 MXN mensuales supuestos = **$49,500 MXN/mes de ingresos brutos hipotéticos**, antes de costos e impuestos. Ni la base de clientes ni la conversión ni la suscripción se acreditaron como reales.','- **DESCONOCIDOS:** mercado alcanzable verificado, adopción, CAC, LTV, churn, margen, disposición de pago, permisos bancarios, seguridad de producción.','- **PRIORIDAD:** piloto medible, aprendizaje de mercado, análisis de costos/retención y sólo después inversión en crecimiento.','- **CONTROL DE CONTENIDO:** representación gráfica conceptual, no captura de operación real, no testimonio, no garantía de retorno o rentabilidad.','', '## Resultado técnico','','- Audio y música sintetizados localmente (sin InVideo).','- Archivos H.264/AAC con subtítulos integrados; 16:9 y 9:16.','- Ver `reports/R041_AUDITORIA_FINAL.json` para hashes y QA verificable.','- Requiere revisión por humano/inversionista; video preparado no equivale a ronda de financiación abierta.'])
 (ROOT/'R041_GUION_Y_AUDITORIA_COMERCIAL.md').write_text('\n'.join(out)+'\n')

if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['assets','audio','video','all'],default='all');opts=ap.parse_args()
 data=dict(scenes=SCENES,seconds=120,product_evidence='R015_R016',business_evidence='MIXED_WITH_HYPOTHESES')
 (REPORTS/'storyboard.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 if opts.stage in ('assets','all'):
  for s in SCENES:make_horizontal(s);make_vertical(s)
  cues=subtitle_files();contact_sheet();print('ASSETS',len(list(ASSETS.glob('*.png'))),'SUBS',len(cues),flush=True)
 if opts.stage in ('audio','all'):
  x=audio_master();print('AUDIO TIMING',[(q['scene'],round(q['raw_voice_seconds'],1),q['budget_seconds'],round(q['tempo'],2)) for q in x],flush=True)
 if opts.stage in ('video','all'):
  outputs={k:render(k) for k in ['h','v']};print('OUTPUTS',[str(x) for x in outputs.values()],flush=True)
  a=do_qa(outputs,subtitle_files(),json.loads((REPORTS/'voice_timing.json').read_text()));write_docs(a)
  print('QA',json.dumps({'result':a['result'],'spoken_words':a['spoken_words'],'files':{k:{field:v[field] for field in ('duration','bytes','sha256')} for k,v in a['files'].items()}},ensure_ascii=False),flush=True)
