#!/usr/bin/env python3
"""Test Polkadot RPC via WebSocket from inside container."""
import socket, json, struct, os, base64, hashlib

def ws_handshake(sock):
    key = base64.b64encode(os.urandom(16)).decode()
    lines = [
        "GET / HTTP/1.1",
        "Host: 127.0.0.1:9933",
        "Upgrade: websocket",
        "Connection: Upgrade",
        f"Sec-WebSocket-Key: {key}",
        "Sec-WebSocket-Version: 13",
        "", ""
    ]
    sock.sendall("\r\n".join(lines).encode())
    resp = sock.recv(4096)
    return b"101" in resp

def ws_send(sock, data):
    payload = data.encode()
    frame = bytearray()
    frame.append(0x81)
    mask_key = os.urandom(4)
    length = len(payload)
    if length <= 125:
        frame.append(0x80 | length)
    elif length <= 65535:
        frame.append(0x80 | 126)
        frame.extend(struct.pack(">H", length))
    frame.extend(mask_key)
    masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    frame.extend(masked)
    sock.sendall(frame)

def ws_recv(sock):
    header = sock.recv(2)
    if len(header) < 2:
        return ""
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", sock.recv(8))[0]
    data = b""
    while len(data) < length:
        chunk = sock.recv(length - len(data))
        if not chunk:
            break
        data += chunk
    return data.decode()

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(10)
sock.connect(("127.0.0.1", 9933))

if ws_handshake(sock):
    print("WS handshake OK")
    req = json.dumps({"jsonrpc": "2.0", "method": "system_health", "params": [], "id": 1})
    ws_send(sock, req)
    resp = ws_recv(sock)
    print(f"health: {resp}")

    req2 = json.dumps({"jsonrpc": "2.0", "method": "system_peers", "params": [], "id": 2})
    ws_send(sock, req2)
    resp2 = ws_recv(sock)
    data = json.loads(resp2)
    peers = data.get("result", [])
    print(f"peers: {len(peers)}")
    for p in peers[:3]:
        print(f"  {p['peerId'][:20]}... role={p.get('roles','?')}")
else:
    print("WS handshake FAILED")

sock.close()
