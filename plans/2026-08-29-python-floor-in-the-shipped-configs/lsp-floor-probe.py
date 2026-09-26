"""Drive basedpyright-langserver the way an editor does and report what it flags live.

Usage: lsp_floor_probe.py <workspace root> <document path inside it>

Opens <document path> as an unsaved buffer (didOpen only, nothing written to disk) holding
syntax that needs Python 3.12, and prints every diagnostic the server publishes for it.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

PROBE = """\
from typing import override


type Alias = int


def ident[T](x: T) -> T:
    return x


class Base:
    def m(self) -> None: ...


class Child(Base):
    @override
    def m(self) -> None: ...
"""


def send(proc, msg):
    body = json.dumps(msg).encode()
    proc.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
    proc.stdin.flush()


def read(proc):
    headers = {}
    while True:
        line = proc.stdout.readline()
        if not line:
            return None
        line = line.decode().strip()
        if not line:
            break
        k, v = line.split(":", 1)
        headers[k.lower()] = v.strip()
    return json.loads(proc.stdout.read(int(headers["content-length"])))


def main():
    root = Path(sys.argv[1]).resolve()
    doc = (root / sys.argv[2]).resolve()
    uri = doc.as_uri()
    proc = subprocess.Popen(
        ["basedpyright-langserver", "--stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=root,
    )
    send(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "processId": None,
                "rootUri": root.as_uri(),
                "workspaceFolders": [{"uri": root.as_uri(), "name": root.name}],
                "capabilities": {"workspace": {"configuration": True}, "textDocument": {"publishDiagnostics": {}}},
            },
        },
    )
    deadline = time.monotonic() + 60
    opened = False
    while time.monotonic() < deadline:
        msg = read(proc)
        if msg is None:
            break
        if msg.get("id") == 1 and "result" in msg:
            send(proc, {"jsonrpc": "2.0", "method": "initialized", "params": {}})
            send(
                proc,
                {
                    "jsonrpc": "2.0",
                    "method": "textDocument/didOpen",
                    "params": {"textDocument": {"uri": uri, "languageId": "python", "version": 1, "text": PROBE}},
                },
            )
            opened = True
        elif "method" in msg and "id" in msg:  # a server->client request: answer it
            result = None
            if msg["method"] == "workspace/configuration":
                result = [None] * len(msg["params"]["items"])
            send(proc, {"jsonrpc": "2.0", "id": msg["id"], "result": result})
        elif opened and msg.get("method") == "textDocument/publishDiagnostics" and msg["params"]["uri"] == uri:
            diags = msg["params"]["diagnostics"]
            print(f"{len(diags)} diagnostic(s) for {doc.relative_to(root)}:")
            for d in diags:
                ln = d["range"]["start"]["line"] + 1
                print(f"  line {ln}: [{d.get('severity')}] {d['message'].splitlines()[0]}")
            break
    else:
        print("timed out waiting for diagnostics")
    proc.kill()


main()
