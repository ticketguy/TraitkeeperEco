from py_vapid import Vapid
from cryptography.hazmat.primitives import serialization
import base64

def generate_vapid_keys():
    vapid = Vapid()
    vapid.generate_keys()

    # Convert private key object to bytes and then to base64 url-safe
    private_bytes = vapid.private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    private_key_b64 = base64.urlsafe_b64encode(private_bytes).decode()

    # Convert public key object to bytes and then to base64 url-safe
    public_bytes = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    public_key_b64 = base64.urlsafe_b64encode(public_bytes).decode()

    print("VAPID Public Key:", public_key_b64)
    print("VAPID Private Key:", private_key_b64)

if __name__ == "__main__":
    generate_vapid_keys()
