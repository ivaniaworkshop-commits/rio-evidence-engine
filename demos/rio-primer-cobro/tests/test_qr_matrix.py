"""Independent QR oracle: compare JS matrix against Python qrcode, fixed QR version 5-L mask 0."""
import json, subprocess, random
from pathlib import Path
import qrcode
from qrcode.util import QRData, MODE_8BIT_BYTE
p=Path(__file__).resolve().parents[1]/'app/qrcode.js'
random.seed(20261105)
chars='ABCDEF0123456789-_=.:'
payloads=['RIO-QR-DEMO|NO-PAGABLE|DEMO-ABC|MXN-CENTAVOS=2500']+[''.join(random.choices(chars,k=random.randint(1,106))) for _ in range(59)]
cmd='const Q=require(process.argv[1]);const values=JSON.parse(process.argv[2]);console.log(JSON.stringify(values.map(p=>Q.matrix(p))));'
raw=subprocess.run(['node','-e',cmd,str(p),json.dumps(payloads)],capture_output=True,text=True,check=True)
matrices=json.loads(raw.stdout)
for idx,(payload,mat) in enumerate(zip(payloads,matrices)):
 qr=qrcode.QRCode(version=5,error_correction=qrcode.constants.ERROR_CORRECT_L,mask_pattern=0,border=0)
 qr.add_data(QRData(payload, mode=MODE_8BIT_BYTE),optimize=0);qr.make(fit=False)
 expected=qr.get_matrix()
 assert len(mat)==37 and mat==expected,f'Case {idx} differs: {payload!r}'
print(json.dumps({'tested':len(payloads),'mismatched':0,'independent_oracle':'python-qrcode','qr_version':5,'ecc':'L','mask':0}))
