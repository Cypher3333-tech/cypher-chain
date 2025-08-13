import argparse
import json
import os
from typing import List
from flask import Flask, request, jsonify
import requests

from .block import Block
from .blockchain import Blockchain
from .transaction import Transaction, TxInput, TxOutput, build_simple_tx
from .wallet import new_wallet
from .config import PERSIST_DIR

app = Flask(__name__)
STATE = {
    "bc": None,
    "peers": set()
}

def data_dir_for_port(port: int) -> str:
    root = os.path.join(PERSIST_DIR, str(port))
    os.makedirs(root, exist_ok=True)
    return root

@app.route("/peers", methods=["GET"])
def peers():
    return jsonify(sorted(list(STATE["peers"])))

@app.route("/peers/add", methods=["POST"])
def peers_add():
    data = request.get_json(force=True)
    url = data.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400
    STATE["peers"].add(url.rstrip("/"))
    return jsonify({"ok": True, "peers": sorted(list(STATE["peers"]))})

def broadcast(path: str, payload: dict):
    dead = []
    for p in list(STATE["peers"]):
        try:
            requests.post(f"{p}{path}", json=payload, timeout=3)
        except Exception:
            dead.append(p)
    for d in dead:
        STATE["peers"].discard(d)

@app.route("/wallet/new", methods=["POST"])
def wallet_new():
    return jsonify(new_wallet())

@app.route("/tx/new", methods=["POST"])
def tx_new():
    data = request.get_json(force=True)
    priv = data.get("private_key")
    pub = data.get("public_key")
    from_addr = data.get("from")
    to_addr = data.get("to")
    amount = int(data.get("amount", 0))
    if not all([priv, pub, from_addr, to_addr]) or amount <= 0:
        return jsonify({"error": "private_key, public_key, from, to, amount required"}), 400
    utxos = {k: v for k, v in STATE["bc"].utxos.items()}
    try:
        tx = build_simple_tx(utxos, priv, pub, to_addr, amount, change_addr=from_addr)
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    ok = STATE["bc"].add_transaction(tx)
    if not ok:
        return jsonify({"error": "tx rejected"}), 400
    broadcast("/tx/broadcast", tx_to_payload(tx))
    return jsonify({"ok": True, "txid": tx.txid})

@app.route("/tx/broadcast", methods=["POST"])
def tx_broadcast():
    data = request.get_json(force=True)
    try:
        tx = payload_to_tx(data)
    except Exception:
        return jsonify({"error": "invalid tx"}), 400
    if STATE["bc"].add_transaction(tx):
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 400

@app.route("/tx/pending", methods=["GET"])
def tx_pending():
    return jsonify([tx_to_payload(t) for t in STATE["bc"].mempool])

@app.route("/mine", methods=["POST"])
def mine():
    data = request.get_json(force=True)
    addr = data.get("miner_address")
    if not addr:
        return jsonify({"error": "miner_address required"}), 400
    blk = STATE["bc"].mine(addr)
    if not blk:
        return jsonify({"error": "mining failed"}), 500
    broadcast("/block/broadcast", block_to_payload(blk))
    return jsonify(block_to_payload(blk))

@app.route("/block/broadcast", methods=["POST"])
def block_broadcast():
    data = request.get_json(force=True)
    try:
        blk = payload_to_block(data)
    except Exception:
        return jsonify({"error": "invalid block"}), 400
    ok = STATE["bc"].try_add_block(blk)
    return jsonify({"ok": ok})

@app.route("/blocks/latest", methods=["GET"])
def blocks_latest():
    return jsonify(block_to_payload(STATE["bc"].latest_block()))

@app.route("/chain", methods=["GET"])
def chain():
    return jsonify([block_to_payload(b) for b in STATE["bc"].chain])

@app.route("/balance/<address>", methods=["GET"])
def balance(address: str):
    return jsonify({"address": address, "balance": STATE["bc"].balance(address)})

def tx_to_payload(tx: Transaction) -> dict:
    return {
        "inputs": [{"txid": i.txid, "vout": i.vout, "signature": i.signature, "pubkey": i.pubkey} for i in tx.inputs],
        "outputs": [{"amount": o.amount, "address": o.address} for o in tx.outputs],
        "timestamp": tx.timestamp,
        "coinbase": tx.coinbase,
        "txid": tx.txid
    }

def payload_to_tx(p: dict) -> Transaction:
    tx = Transaction(
        inputs=[TxInput(**i) for i in p["inputs"]],
        outputs=[TxOutput(**o) for o in p["outputs"]],
        timestamp=p["timestamp"],
        coinbase=p.get("coinbase", False),
    )
    tx.txid = p.get("txid") or tx.compute_txid()
    return tx

def block_to_payload(b: Block) -> dict:
    return {
        "index": b.index,
        "prev_hash": b.prev_hash,
        "timestamp": b.timestamp,
        "nonce": b.nonce,
        "txs": [tx_to_payload(t) for t in b.txs],
        "merkle_root": b.merkle_root,
        "hash": b.hash
    }

def payload_to_block(p: dict) -> Block:
    txs = [payload_to_tx(t) for t in p["txs"]]
    b = Block(index=p["index"], prev_hash=p["prev_hash"], timestamp=p["timestamp"],
              nonce=p["nonce"], txs=txs, merkle_root=p["merkle_root"], hash=p["hash"])
    return b

def main():
    parser = argparse.ArgumentParser(description="Cypher node")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--peers", type=str, nargs="*", default=[])
    args = parser.parse_args()

    data_dir = os.path.join(".data", str(args.port))
    os.makedirs(data_dir, exist_ok=True)
    bc = Blockchain(data_dir)
    STATE["bc"] = bc
    for p in args.peers:
        STATE["peers"].add(p.rstrip("/"))

    print(f"Starting Cypher node on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port)

if __name__ == "__main__":
    main()