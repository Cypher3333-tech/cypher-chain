import json
import os
import time
from typing import Dict, Tuple, List, Optional
from .block import Block, mine_block
from .transaction import Transaction, TxOutput, make_coinbase
from .utils import ensure_dir
from .config import DIFFICULTY, BLOCK_REWARD, PERSIST_DIR, GENESIS_MESSAGE

UTXOKey = Tuple[str, int]

class Blockchain:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        ensure_dir(self.data_dir)
        self.chain_path = os.path.join(self.data_dir, "chain.json")
        self.utxo_path = os.path.join(self.data_dir, "utxos.json")
        self.txs_path = os.path.join(self.data_dir, "mempool.json")
        self.chain: List[Block] = []
        self.utxos: Dict[UTXOKey, TxOutput] = {}
        self.mempool: List[Transaction] = []
        self._load_or_init()

    def _load_or_init(self):
        if os.path.exists(self.chain_path):
            self._load()
        else:
            self._init_genesis()

    def _load(self):
        with open(self.chain_path, "r") as f:
            raw = json.load(f)
        self.chain = []
        for b in raw["chain"]:
            txs = []
            for t in b["txs"]:
                tx = Transaction(
                    inputs=[type("TxInput", (), i) for i in t["inputs"]],
                    outputs=[TxOutput(**o) for o in t["outputs"]],
                    timestamp=t["timestamp"],
                    coinbase=t.get("coinbase", False),
                    txid=t.get("txid")
                )
                txs.append(tx)
            blk = Block(index=b["index"], prev_hash=b["prev_hash"], timestamp=b["timestamp"],
                        nonce=b["nonce"], txs=txs, merkle_root=b["merkle_root"], hash=b["hash"])
            self.chain.append(blk)
        with open(self.utxo_path, "r") as f:
            raw_utxos = json.load(f)
        self.utxos = {(k.split(":")[0], int(k.split(":")[1])): TxOutput(**v) for k, v in raw_utxos.items()}
        if os.path.exists(self.txs_path):
            with open(self.txs_path, "r") as f:
                raw_mempool = json.load(f)
            self.mempool = []
            for t in raw_mempool:
                tx = Transaction(
                    inputs=[type("TxInput", (), i) for i in t["inputs"]],
                    outputs=[TxOutput(**o) for o in t["outputs"]],
                    timestamp=t["timestamp"],
                    coinbase=t.get("coinbase", False),
                    txid=t.get("txid")
                )
                self.mempool.append(tx)
        else:
            self.mempool = []

    def _persist(self):
        raw_chain = {
            "chain": [
                {
                    "index": b.index,
                    "prev_hash": b.prev_hash,
                    "timestamp": b.timestamp,
                    "nonce": b.nonce,
                    "txs": [t.to_dict(include_sig=True) | {"txid": t.txid} for t in b.txs],
                    "merkle_root": b.merkle_root,
                    "hash": b.hash
                } for b in self.chain
            ]
        }
        with open(self.chain_path, "w") as f:
            json.dump(raw_chain, f, indent=2)
        raw_utxos = {f"{txid}:{vout}": {"amount": out.amount, "address": out.address}
                     for (txid, vout), out in self.utxos.items()}
        with open(self.utxo_path, "w") as f:
            json.dump(raw_utxos, f, indent=2)
        with open(self.txs_path, "w") as f:
            json.dump([t.to_dict(include_sig=True) | {"txid": t.txid} for t in self.mempool], f, indent=2)

    def _init_genesis(self):
        genesis_tx = Transaction(inputs=[], outputs=[], coinbase=True, timestamp=time.time())
        genesis_tx.txid = genesis_tx.compute_txid()
        genesis = Block(index=0, prev_hash=GENESIS_MESSAGE, timestamp=time.time(), txs=[genesis_tx])
        genesis = mine_block(genesis, DIFFICULTY)
        self.chain = [genesis]
        self.utxos = {}
        self.mempool = []
        self._persist()

    def latest_block(self) -> Block:
        return self.chain[-1]

    def add_transaction(self, tx: Transaction) -> bool:
        if not tx.txid:
            tx.txid = tx.compute_txid()
        if tx.coinbase:
            return False
        if not tx.verify(self.utxos):
            return False
        if any(t.txid == tx.txid for t in self.mempool):
            return False
        spent_in_mempool = {(i.txid, i.vout) for t in self.mempool for i in t.inputs}
        for i in tx.inputs:
            if (i.txid, i.vout) in spent_in_mempool:
                return False
        self.mempool.append(tx)
        self._persist()
        return True

    def apply_tx(self, tx: Transaction) -> bool:
        if tx.coinbase:
            for idx, o in enumerate(tx.outputs):
                self.utxos[(tx.txid, idx)] = o
            return True
        if not tx.verify(self.utxos):
            return False
        for i in tx.inputs:
            ref = (i.txid, i.vout)
            if ref not in self.utxos:
                return False
            del self.utxos[ref]
        for idx, o in enumerate(tx.outputs):
            self.utxos[(tx.txid, idx)] = o
        return True

    def validate_block(self, block: Block, prev: Block) -> bool:
        if block.prev_hash != prev.hash:
            return False
        if not block.hash or not block.hash.startswith("0" * DIFFICULTY):
            return False
        if block.compute_hash() != block.hash:
            return False
        if block.compute_merkle() != block.merkle_root:
            return False
        if not block.txs or not block.txs[0].coinbase:
            return False
        reward_out = sum(o.amount for o in block.txs[0].outputs)
        if reward_out != BLOCK_REWARD:
            return False
        utxo_copy = dict(self.utxos)
        for tx in block.txs:
            if not tx.coinbase and not tx.verify(utxo_copy):
                return False
            if tx.coinbase:
                for idx, o in enumerate(tx.outputs):
                    utxo_copy[(tx.txid, idx)] = o
            else:
                for i in tx.inputs:
                    ref = (i.txid, i.vout)
                    if ref not in utxo_copy:
                        return False
                    del utxo_copy[ref]
                for idx, o in enumerate(tx.outputs):
                    utxo_copy[(tx.txid, idx)] = o
        return True

    def mine(self, miner_address: str):
        coinbase = make_coinbase(miner_address, BLOCK_REWARD)
        selected: List[Transaction] = [coinbase]
        utxo_temp = dict(self.utxos)
        for tx in list(self.mempool):
            if tx.verify(utxo_temp):
                for i in tx.inputs:
                    del utxo_temp[(i.txid, i.vout)]
                for idx, o in enumerate(tx.outputs):
                    utxo_temp[(tx.txid, idx)] = o
                selected.append(tx)
        block = Block(index=len(self.chain),
                      prev_hash=self.latest_block().hash,
                      timestamp=time.time(),
                      txs=selected)
        mined = mine_block(block, DIFFICULTY)
        if self.validate_block(mined, self.latest_block()):
            for tx in selected:
                self.apply_tx(tx)
                self.mempool = [t for t in self.mempool if t.txid != tx.txid]
            self.chain.append(mined)
            self._persist()
            return mined
        return None

    def try_add_block(self, block: Block) -> bool:
        if block.index != len(self.chain):
            return False
        if not self.validate_block(block, self.latest_block()):
            return False
        for tx in block.txs:
            self.apply_tx(tx)
            self.mempool = [t for t in self.mempool if t.txid != tx.txid]
        self.chain.append(block)
        self._persist()
        return True

    def balance(self, address: str) -> int:
        return sum(out.amount for out in self.utxos.values() if out.address == address)
