from pathlib import Path
base=Path(__file__).resolve().parent.parent
html=(base/'app/index.html').read_text(encoding='utf-8')
html=html.replace('<link rel="stylesheet" href="style.css">','<style>'+(base/'app/style.css').read_text(encoding='utf-8')+'</style>')
for f in ['logic','chat','qrcode','persistence','app']:
 html=html.replace(f'<script src="{f}.js"></script>','<script>\n'+(base/'app'/f'{f}.js').read_text(encoding='utf-8')+'\n</script>')
(base/'RIO_PRIMER_COBRO_R014_OFFLINE.html').write_text(html,encoding='utf-8')
print('Generated',base/'RIO_PRIMER_COBRO_R014_OFFLINE.html')
