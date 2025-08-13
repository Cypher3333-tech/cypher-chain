import hashlib
import json
import os
from typing import List

def sha256d_hex(data: bytes) -> str:
    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()

def ripemd160(data: bytes) -> bytes:
    h = hashlib.new('ripemd160')
    h.update(data)
    return h.digest()

def to_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))

def merkle_root_hex(txids: List[str]) -> str:
    if not txids:
        return sha256d_hex(b"")
    level = txids[:]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i+1] if i+1 < len(level) else left
            nxt.append(sha256d_hex(bytes.fromhex(left) + bytes.fromhex(right)))
        level = nxt
    return level[0]

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)
