#!/usr/bin/env python3
# mcp-archaeologist-cli.py — Анализ истории кода через git
import json
import sys
import subprocess
from datetime import datetime

def blame_line(file, line, repo="."):
    try:
        result = subprocess.run(
            ["git", "blame", "-L", f"{line},{line}", "--porcelain", file],
            cwd=repo, capture_output=True, text=True
        )
        return result.stdout or "Нет данных"
    except Exception as e:
        return f"Ошибка: {e}"

def code_ownership(path, repo="."):
    try:
        result = subprocess.run(
            ["git", "shortlog", "-sn", "--", path],
            cwd=repo, capture_output=True, text=True
        )
        return result.stdout or "Нет данных"
    except Exception as e:
        return f"Ошибка: {e}"

def commit_history(file, limit=10, repo="."):
    try:
        result = subprocess.run(
            ["git", "log", f"-{limit}", "--oneline", "--", file],
            cwd=repo, capture_output=True, text=True
        )
        return result.stdout or "Нет коммитов"
    except Exception as e:
        return f"Ошибка: {e}"

def temporal_coupling(file1, file2, repo=".", since=""):
    try:
        since_arg = f"--since={since}" if since else ""
        def get_commits(f):
            out = subprocess.run(
                ["git", "log", "--format=%H", since_arg, "--", f],
                cwd=repo, capture_output=True, text=True
            )
            return set(out.stdout.strip().split())
        commits1 = get_commits(file1)
        commits2 = get_commits(file2)
        if not commits1 or not commits2:
            return "Недостаточно данных"
        inter = len(commits1 & commits2)
        union = len(commits1 | commits2)
        coupling = inter / union if union > 0 else 0.0
        return f"Coupling: {coupling:.2f} (совместных: {inter})"
    except Exception as e:
        return f"Ошибка: {e}"

TOOLS = {
    "blame_line": blame_line,
    "code_ownership": code_ownership,
    "commit_history": commit_history,
    "temporal_coupling": temporal_coupling,
}

def handle_request(request):
    method = request.get("method")
    req_id = request.get("id")
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {"tools": [{"name": n} for n in TOOLS.keys()]},
            "id": req_id
        }
    elif method == "tools/call":
        tool = request.get("params", {}).get("name")
        args = request.get("params", {}).get("arguments", {})
        if tool in TOOLS:
            try:
                result = TOOLS[tool](**args)
                return {
                    "jsonrpc": "2.0",
                    "result": {"content": [{"type": "text", "text": result}]},
                    "id": req_id
                }
            except Exception as e:
                return {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": req_id}
        else:
            return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unknown tool: {tool}"}, "id": req_id}
    else:
        return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unknown method: {method}"}, "id": req_id}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            print(json.dumps(resp), flush=True)
        except Exception as e:
            print(json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": str(e)}}), flush=True)

if __name__ == "__main__":
    main()
