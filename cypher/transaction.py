import time
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from ecdsa import SigningKey, VerifyingKey, SECP256k1, BadSignatureError
import hashlib
from .utils import sha256d_hex, to_json, ripemd160

def pubkey_to_address(pubkey_hex: str) -> str:
    pub_bytes = bytes.fromhex(pubkey_hex)
    h = ripemd160(hashlib.sha256(pub_bytes).digest()).hex()
    return "CYPH" + h

@dataclass
class TxInput:
    txid: str
    vout: int
    signature: Optional[str] = None
    pubkey: Optional[str] = None

    def to_dict(self, include_sig=True):
        d = {"txid": self.txid, "vout": self.vout}
        if include_sig:
            d.update({"signature": self.signature, "pubkey": self.pubkey})
        return d

@dataclass
class TxOutput:
    amount: int
    address: str

    def to_dict(self):
        return {"amount": self.amount, "address": self.address}

@dataclass
class Transaction:
    inputs: List[TxInput]
    outputs: List[TxOutput]
    timestamp: float = field(default_factory=lambda: time.time())
    txid: Optional[str] = None
    coinbase: bool = False

    def to_dict(self, include_sig=True):
        return {
            "inputs": [i.to_dict(include_sig=include_sig) for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
            "timestamp": self.timestamp,
            "coinbase": self.coinbase,
        }

    def compute_txid(self) -> str:
        # Exclude signatures for ID preimage
        preimage = to_json(self.to_dict(include_sig=False)).encode()
        return sha256d_hex(preimage)

    def sign_inputs(self, priv_hex: str, utxo_map: Dict[Tuple[str,int], TxOutput]):
        if self.coinbase:
            self.txid = self.compute_txid()
            return
        sk = SigningKey.from_string(bytes.fromhex(priv_hex), curve=SECP256k1)
        vk = sk.get_verifying_key()
        pub_hex = vk.to_string().hex()
        from_addr = pubkey_to_address(pub_hex)
        # Validate that all inputs belong to from_addr
        for tin in self.inputs:
            ref = (tin.txid, tin.vout)
            if ref not in utxo_map:
                raise ValueError("Referenced UTXO not found")
            if utxo_map[ref].address != from_addr:
                raise ValueError("Attempting to spend UTXO not owned by provided key")
        # Sign preimage
        preimage = to_json(self.to_dict(include_sig=False)).encode()
        sig = sk.sign_deterministic(preimage).hex()
        for tin in self.inputs:
            tin.signature = sig
            tin.pubkey = pub_hex
        self.txid = self.compute_txid()

    def verify(self, utxo_map: Dict[Tuple[str,int], TxOutput]) -> bool:
        if self.coinbase:
            # coinbase has no inputs; extra checks done at block validation
            return True
        try:
            # Verify signatures and ownership
            preimage = to_json(self.to_dict(include_sig=False)).encode()
            total_in = 0
            for tin in self.inputs:
                ref = (tin.txid, tin.vout)
                if ref not in utxo_map:
                    return False
                utxo = utxo_map[ref]
                total_in += utxo.amount
                if not tin.signature or not tin.pubkey:
                    return False
                vk = VerifyingKey.from_string(bytes.fromhex(tin.pubkey), curve=SECP256k1)
                vk.verify(bytes.fromhex(tin.signature), preimage)
                if pubkey_to_address(tin.pubkey) != utxo.address:
                    return False
            total_out = sum(o.amount for o in self.outputs)
            if total_out > total_in:
                return False
            # txid consistent
            return self.compute_txid() == self.txid
        except BadSignatureError:
            return False
        except Exception:
            return False

def make_coinbase(to_address: str, amount: int) -> Transaction:
    tx = Transaction(inputs=[], outputs=[TxOutput(amount=amount, address=to_address)], coinbase=True)
    tx.txid = tx.compute_txid()
    return tx

def build_simple_tx(utxos: Dict[Tuple[str,int], TxOutput], from_priv_hex: str, from_pub_hex: str, to_addr: str, amount: int, change_addr: Optional[str]=None) -> Transaction:
    # Collect inputs until amount is covered
    owner_addr = pubkey_to_address(from_pub_hex)
    available = [(k,v) for k,v in utxos.items() if v.address == owner_addr]
    total = 0
    ins: List[TxInput] = []
    for (txid, vout), out in available:
        ins.append(TxInput(txid=txid, vout=vout))
        total += out.amount
        if total >= amount:
            break
    if total < amount:
        raise ValueError("Insufficient funds")
    outputs = [TxOutput(amount=amount, address=to_addr)]
    change = total - amount
    if change > 0:
        outputs.append(TxOutput(amount=change, address=change_addr or owner_addr))
    tx = Transaction(inputs=ins, outputs=outputs)
    tx.sign_inputs(from_priv_hex, utxos)
    return tx

def generate_keypair() -> Tuple[str,str,str]:
    sk = SigningKey.generate(curve=SECP256k1)
    vk = sk.get_verifying_key()
    priv_hex = sk.to_string().hex()
    pub_hex = vk.to_string().hex()
    addr = pubkey_to_address(pub_hex)
    return priv_hex, pub_hex, addr