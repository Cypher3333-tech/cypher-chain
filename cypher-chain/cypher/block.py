import time
from dataclasses import dataclass, field
from typing import List, Optional
from .utils import sha256d_hex, merkle_root_hex, to_json
from .transaction import Transaction

@dataclass
class Block:
    index: int
    prev_hash: str
    timestamp: float
    nonce: int = 0
    txs: List[Transaction] = field(default_factory=list)
    merkle_root: Optional[str] = None
    hash: Optional[str] = None

    def compute_merkle(self) -> str:
        txids = [tx.txid for tx in self.txs]
        return merkle_root_hex(txids)

    def header_preimage(self) -> bytes:
        header = {
            "index": self.index,
            "prev_hash": self.prev_hash,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "merkle_root": self.merkle_root or "",
        }
        return to_json(header).encode()

    def compute_hash(self) -> str:
        return sha256d_hex(self.header_preimage())

    def finalize(self):
        self.merkle_root = self.compute_merkle()
        self.hash = self.compute_hash()

def mine_block(block: Block, difficulty: int) -> Block:
    prefix = "0" * difficulty
    block.merkle_root = block.compute_merkle()
    block.nonce = 0
    while True:
        h = block.compute_hash()
        if h.startswith(prefix):
            block.hash = h
            return block
        block.nonce += 1
        if block.nonce % 100000 == 0:
            block.timestamp = time.time()
