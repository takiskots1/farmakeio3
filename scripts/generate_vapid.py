#!/usr/bin/env python3
"""Generate VAPID private key and public key using cryptography (from pywebpush deps)."""
import base64
import os
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat

root = Path(__file__).resolve().parent.parent
key_file = root / 'instance' / 'vapid_private.pem'
key_file.parent.mkdir(parents=True, exist_ok=True)
if key_file.exists():
    print('Υπάρχει ήδη ιδιωτικό κλειδί:', key_file)
    raise SystemExit('Δεν το αντικαθιστούμε γιατί θα ακυρωθούν οι υπάρχουσες push συνδρομές.')
private_key = ec.generate_private_key(ec.SECP256R1())
key_file.write_bytes(private_key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
os.chmod(key_file, 0o600)
public_raw = private_key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
public_key = base64.urlsafe_b64encode(public_raw).rstrip(b'=').decode('ascii')
print('VAPID_PRIVATE_KEY=instance/vapid_private.pem')
print('VAPID_PUBLIC_KEY=' + public_key)
print('VAPID_CONTACT=mailto:info@chryspharmacy.gr')
