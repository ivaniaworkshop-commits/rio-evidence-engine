"""Optional interop check against the official Standard Webhooks Python SDK.

Requires the separately installed `standardwebhooks` package. Uses fixtures only.
"""
import base64
import importlib.metadata
import time
from datetime import datetime, timezone

from standardwebhooks.webhooks import Webhook, WebhookVerificationError

from rio_pey_codi.signatures import InvalidWebhook, make_signature, verify_and_capture, verify_signature

secret = 'whsec_' + base64.b64encode(b'synthetic-interop-secret-material-32').decode()
message_id = 'msg_synthetic_interop'
timestamp = int(time.time())
body = b'{"type":"synthetic.example","data":{"amount":150}}'
official = Webhook(secret)
official_signature = official.sign(message_id, datetime.fromtimestamp(timestamp, timezone.utc), body.decode('utf-8'))
headers = {'webhook-id':message_id, 'webhook-timestamp':str(timestamp), 'webhook-signature':official_signature}
assert verify_signature(headers, body, secret, now=timestamp) == message_id
identity, evidence = verify_and_capture(headers, body, secret, 'synthetic-v1', now=timestamp)
assert identity == message_id and evidence.signature == official_signature
headers['webhook-signature'] = make_signature(secret, message_id, timestamp, body)
assert official.verify(body, headers)['type'] == 'synthetic.example'
for callback, error_type in (
    (lambda: verify_signature(headers, body + b' ', secret, now=timestamp), InvalidWebhook),
    (lambda: official.verify(body + b' ', headers), WebhookVerificationError),
):
    try:
        callback()
    except error_type:
        pass
    else:
        raise AssertionError('Altered body accepted')
print('OFFICIAL_STANDARD_WEBHOOKS_INTEROP_OK', importlib.metadata.version('standardwebhooks'))
