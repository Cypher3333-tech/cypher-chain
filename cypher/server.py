import os
from flask import Flask
import threading
from cypher import node

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Cypher node is running!"

def start_node():
    node.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    threading.Thread(target=start_node).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
