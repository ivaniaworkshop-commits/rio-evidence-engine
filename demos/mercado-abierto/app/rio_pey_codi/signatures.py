"""Standard Webhooks HMAC v1 verifier; confirm provider-specific contract before LIVE."""
import base64
import hashlib
import hmac
import re
import time
from dataclasses import dataclass


class InvalidWebhook(ValueError):
    pass


@dataclass(frozen=True, repr=False)
class SignatureEvidence:
    signature: str
    timestamp: int
    received_at: int
    key_ref: str


def _secret_bytes(secret: str) -> bytes:
    try:
        if not isinstance(secret, str):
            raise ValueError('Invalid secret type')
        value = secret.removeprefix('whsec_')
        if not re.fullmatch(r'[A-Za-z0-9+/]+={0,2}', value):
            raise ValueError('Invalid base64')
        bare = value.rstrip('=')
        padding = (-len(bare)) % 4
        if padding == 3 or len(value) - len(bare) not in (0, padding):
            raise ValueError('Invalid padding')
        decoded = base64.b64decode(bare + '=' * padding, validate=True)
        if base64.b64encode(decoded).decode('ascii').rstrip('=') != bare:
            raise ValueError('Noncanonical base64')
        return decoded
    except (ValueError, base64.binascii.Error, UnicodeError) as exc:
        raise InvalidWebhook("Webhook secret must be base64 or whsec_base64") from exc


def valid_key_ref(value):
    return (isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9._-]{1,64}', value) is not None
            and not value.startswith('whsec_'))


def validate_webhook_keyring(active_ref, active_secret, historical_keys):
    """Validate references and key material without exposing their values."""
    if not valid_key_ref(active_ref):
        raise ValueError('A non-secret webhook signing key reference is required')
    if not isinstance(active_secret, str) or len(active_secret) > 512:
        raise ValueError('Invalid webhook signing key configuration')
    if type(historical_keys) is not tuple or len(historical_keys) > 8:
        raise ValueError('Invalid historical webhook signing key configuration')
    seen_refs = {active_ref}
    materials = []
    try:
        if active_secret:
            active_material = _secret_bytes(active_secret)
            if not 24 <= len(active_material) <= 64:
                raise InvalidWebhook('Invalid key length')
            materials.append(active_material)
        for entry in historical_keys:
            if type(entry) is not tuple or len(entry) != 2:
                raise InvalidWebhook('Invalid entry')
            ref, secret = entry
            if (not valid_key_ref(ref) or ref in seen_refs or not isinstance(secret, str)
                    or not secret or len(secret) > 512):
                raise InvalidWebhook('Invalid key')
            material = _secret_bytes(secret)
            if not 24 <= len(material) <= 64 or any(hmac.compare_digest(material, prior) for prior in materials):
                raise InvalidWebhook('Duplicate or empty key')
            seen_refs.add(ref)
            materials.append(material)
    except (InvalidWebhook, TypeError, ValueError, UnicodeError):
        raise ValueError('Invalid webhook signing key configuration') from None


def make_signature(secret: str, message_id: str, timestamp: int, raw_body: bytes) -> str:
    """Test fixture / helper, not a proof that pey currently uses Standard Webhooks v1."""
    payload = message_id.encode() + b"." + str(timestamp).encode() + b"." + raw_body
    mac = hmac.new(_secret_bytes(secret), payload, hashlib.sha256).digest()
    return "v1," + base64.b64encode(mac).decode("ascii")


def verify_signature(headers: dict[str, str], raw_body: bytes, secret: str, *, now: int | None = None, tolerance_s: int = 300) -> str:
    normalized = {k.lower(): v for k, v in headers.items()}
    event_id = normalized.get("webhook-id", "")
    timestamp_s = normalized.get("webhook-timestamp", "")
    signature_header = normalized.get("webhook-signature", "")
    if not event_id or not timestamp_s or not signature_header or len(event_id) > 200:
        raise InvalidWebhook("Missing signature metadata")
    if not timestamp_s.isascii() or not timestamp_s.isdigit() or len(timestamp_s) > 12:
        raise InvalidWebhook("Invalid timestamp")
    timestamp = int(timestamp_s)
    current = int(time.time()) if now is None else now
    if abs(current - timestamp) > tolerance_s:
        raise InvalidWebhook("Webhook timestamp outside allowed window")
    expected = make_signature(secret, event_id, timestamp, raw_body).split(",", 1)[1]
    # Multiple signatures are permitted during key rotation, but every candidate must be valid base64 text.
    candidates = [part.strip().split(",", 1) for part in signature_header.split(" ") if part.strip()]
    if not any(len(pair) == 2 and pair[0] == "v1" and hmac.compare_digest(pair[1], expected) for pair in candidates):
        raise InvalidWebhook("Invalid webhook signature")
    return event_id


def verify_and_capture(headers, raw_body, secret, key_ref, *, now=None):
    """Verify a fresh delivery and retain only one matching MAC, never the secret."""
    received_at = int(time.time()) if now is None else now
    event_id = verify_signature(headers, raw_body, secret, now=received_at)
    timestamp = int(headers['webhook-timestamp'])
    return event_id, SignatureEvidence(make_signature(secret, event_id, timestamp, raw_body),
                                       timestamp, received_at, key_ref)


def reverify_stored_events(events, secret, key_ref, *, historical_keys=(), now=None):
    """Recheck stored MACs using the recorded reception time, not today's time.

    This verifies possession of the configured shared secret; it does not prove
    bank settlement, identify the payer, or bind a provider account to a tenant.
    Reception time itself is a server/database assertion, not signed by pey.
    """
    if not events or len(events) > 100:
        return 'NOT_CHECKED'
    # References select exactly one key; never try other secrets as a fallback.
    historical = dict(historical_keys)
    current = int(time.time()) if now is None else now
    outcomes = set()
    for event in events:
        values = (event.signature, event.signature_timestamp,
                  event.signature_received_at, event.signature_key_ref)
        if all(value is None for value in values):
            outcomes.add('NOT_RECORDED')
            continue
        if (any(value is None for value in values) or
                not isinstance(event.signature, str) or not re.fullmatch(r'v1,[A-Za-z0-9+/]{43}=', event.signature) or
                type(event.signature_timestamp) is not int or type(event.signature_received_at) is not int or
                event.signature_timestamp <= 0 or event.signature_received_at <= 0 or
                event.signature_received_at > current + 300 or
                not isinstance(event.signature_key_ref, str) or
                not re.fullmatch(r'[A-Za-z0-9._-]{1,64}', event.signature_key_ref)):
            outcomes.add('INVALID')
            continue
        event_secret = secret if event.signature_key_ref == key_ref else historical.get(event.signature_key_ref)
        if not event_secret:
            outcomes.add('KEY_UNAVAILABLE')
            continue
        try:
            if event.raw_body is None:
                raise InvalidWebhook('Missing signed bytes')
            raw = bytes(event.raw_body)
            if len(raw) > 65536:
                raise InvalidWebhook('Oversized signed bytes')
            verify_signature({'webhook-id':event.id,
                              'webhook-timestamp':str(event.signature_timestamp),
                              'webhook-signature':event.signature}, raw, event_secret,
                             now=event.signature_received_at)
        except (InvalidWebhook, TypeError, ValueError, UnicodeError, OverflowError):
            outcomes.add('INVALID')
        else:
            outcomes.add('VERIFIED')
    # Mixed evidence is not promoted by one valid signature.
    for status in ('INVALID', 'KEY_UNAVAILABLE', 'NOT_RECORDED'):
        if status in outcomes:
            return status
    return 'VERIFIED'
