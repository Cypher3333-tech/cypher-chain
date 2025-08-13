from typing import Dict
from .transaction import generate_keypair

def new_wallet() -> Dict[str,str]:
    priv, pub, addr = generate_keypair()
    return {"private_key": priv, "public_key": pub, "address": addr}
