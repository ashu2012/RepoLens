If you're using **Python**, there are several excellent cross-platform IPC libraries. For your **RepoLens daemon (single server + multiple clients)**, these are the best choices:

| Library | Windows | Linux | macOS | Performance | Recommendation |
|---------|----------|--------|--------|-------------|----------------|
| **ZeroMQ (pyzmq)** ⭐⭐⭐⭐⭐ | ✅ | ✅ | ✅ | Excellent | **Best overall** |
| **multiprocessing.connection** | ✅ | ✅ | ✅ | Very good | Built into Python |
| **RPyC** | ✅ | ✅ | ✅ | Good | Python RPC |
| **Pyro5** | ✅ | ✅ | ✅ | Good | Distributed objects |
| **gRPC** | ✅ | ✅ | ✅ | Good | Cross-language |
| **aiohttp/WebSocket** | ✅ | ✅ | ✅ | Moderate | Simple |
| **Redis** | ✅ | ✅ | ✅ | Moderate | Overkill for local IPC |

## 1. ZeroMQ (Recommended) ⭐⭐⭐⭐⭐

Install:

```bash id="1kbjdo"
pip install pyzmq
```

Server:

```python id="hbe7km"
import zmq

ctx = zmq.Context()

socket = ctx.socket(zmq.REP)
socket.bind("ipc:///tmp/repolens.sock")      # Linux/macOS
# socket.bind("tcp://127.0.0.1:5555")        # Windows

while True:
    msg = socket.recv_json()
    socket.send_json({"status": "ok"})
```

Client:

```python id="8emdmh"
socket = ctx.socket(zmq.REQ)
socket.connect("ipc:///tmp/repolens.sock")
socket.send_json({"cmd": "search"})
reply = socket.recv_json()
```

### Advantages

- Same API on every OS
- Automatically uses efficient transports
- Supports:
  - IPC
  - TCP
  - In-process
  - Multicast
- Handles reconnects
- Extremely mature (used in finance and distributed systems)

---

## 2. Python's built-in `multiprocessing.connection`

No installation required.

```python id="kmgr04"
from multiprocessing.connection import Listener

listener = Listener(("localhost", 6000))

while True:
    conn = listener.accept()
    print(conn.recv())
    conn.send("OK")
```

Client:

```python id="yc6oz5"
from multiprocessing.connection import Client

conn = Client(("localhost", 6000))
conn.send("hello")
print(conn.recv())
```

Works on:

- Windows
- Linux
- macOS

Very simple, but limited to Python clients.

---

## 3. RPyC

Install:

```bash id="lbskv1"
pip install rpyc
```

Lets you call methods on another Python process almost as if they were local functions.

```python id="beiua3"
conn.root.semantic_search("payment retry")
```

Very convenient for Python-only ecosystems.

---

## 4. Pyro5

```bash id="c4rogp"
pip install Pyro5
```

Provides remote Python objects and automatic serialization. Good for larger Python applications.

---

## 5. gRPC

If you expect clients in:

- Java
- Go
- Rust
- Node.js
- Python

then gRPC is an excellent choice.

``` id="l3s3lb"
CLI
VSCode
Cursor
MCP
Java
Python

↓

gRPC

↓

RepoLens Daemon
```

---

# Single instance detection

A reliable cross-platform approach is to combine a file lock with an IPC connection.

```python id="83laqj"
from filelock import FileLock

lock = FileLock("repolens.lock")

try:
    with lock.acquire(timeout=0):
        # First instance
        start_server()

except Timeout:
    # Another instance owns the lock
    connect_to_server()
```

Install:

```bash id="ryfh0y"
pip install filelock
```

`filelock` works on:

- Windows
- Linux
- macOS

---

# My recommendation for RepoLens

``` id="jkirzu"
            RepoLens Daemon
        ------------------------
        Vector DB
        Symbol Index
        Git Watcher
        Embedding Cache
        ------------------------
              ZeroMQ
          ipc:// or tcp://
               ▲
    ┌──────────┼───────────┐
    │          │           │
 CLI       VSCode      MCP Server
 Cursor     Codex       Agents
```

- **Leader election:** `filelock`
- **IPC:** **ZeroMQ (pyzmq)**
- **Serialization:** MessagePack or Protocol Buffers (faster and smaller than JSON)
- **Fallback transport:** On Windows, if IPC sockets are inconvenient, use `tcp://127.0.0.1:<port>` with the exact same ZeroMQ API.

This combination gives you a clean, OS-independent solution with minimal platform-specific code while remaining fast enough to serve many concurrent semantic search requests.