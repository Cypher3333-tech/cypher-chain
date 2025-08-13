# Cypher blockchain
Minimal Bitcoin-like blockchain with PoW, UTXOs, wallets, and HTTP networking.

## Quickstart
1. python -m venv .venv
2. .\.venv\Scripts\Activate.ps1
3. pip install -r requirements.txt
4. python -m cypher.node --port 5001
5. python -m cypher.node --port 5002 --peers http://127.0.0.1:5001