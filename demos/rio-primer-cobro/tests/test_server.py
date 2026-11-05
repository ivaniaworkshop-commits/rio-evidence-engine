"""Local-only HTTP contract checks. No OpenAI or payment API request is made."""
import json, pathlib, subprocess, urllib.request, urllib.error, time
R=pathlib.Path(__file__).resolve().parents[1]
p=subprocess.Popen(['node',str(R/'server'/'dev_server.mjs')],cwd=R,stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT)
try:
 for _ in range(30):
  try:
   with urllib.request.urlopen('http://127.0.0.1:8787/api/health',timeout=.1) as q: data=json.load(q);break
  except: time.sleep(.1)
 else: raise RuntimeError('No local HTTP server available')
 assert data['paymentIntegration'] is False
 assert data['engine']=='LOCAL_RULES_ONLY'
 with urllib.request.urlopen('http://127.0.0.1:8787/',timeout=2) as r:
  assert r.status==200
  assert b'R\xc3\x8dO' in r.read()
 question=json.dumps({'question':'¿Ya me pagaron?','state':'DIGITAL_DEMO_PENDING','method':'digital'}).encode()
 req=urllib.request.Request('http://127.0.0.1:8787/api/help',data=question,headers={'content-type':'application/json'})
 try: urllib.request.urlopen(req,timeout=2);assert False,'No key should not generate AI'
 except urllib.error.HTTPError as e:
  assert e.code==503
  assert 'NO CONFIGURADA' in e.read().decode()
 req=urllib.request.Request('http://127.0.0.1:8787/api/help',data=b'x'*5000,headers={'content-type':'application/json'})
 try: urllib.request.urlopen(req,timeout=2);assert False,'Large input must reject'
 except urllib.error.HTTPError as e: assert e.code==413
 print(json.dumps({'status':'PASS','checks':5,'openai_calls':0,'payment_calls':0,'listens':'127.0.0.1:8787'}))
finally:
 p.terminate();p.wait(timeout=5)
