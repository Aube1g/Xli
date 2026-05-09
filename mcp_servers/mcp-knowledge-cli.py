#!/usr/bin/env python3
# mcp-knowledge-base-cli.py — семантический поиск по коду
import json
import sys
import re
from pathlib import Path
from collections import defaultdict

# Простая инвертированная индексная база
class SimpleIndex:
    def __init__(self, root_dir="."):
        self.root_dir = Path(root_dir)
        self.index = defaultdict(set)  # token -> set(file paths)
        self.file_cache = {}            # file path -> content
        self._build()
    
    def _tokenize(self, text):
        """разбиваем на слова/идентификаторы"""
        return set(re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{2,}\b', text.lower()))
    
    def _build(self):
        for py_file in self.root_dir.rglob("*.py"):
            if "venv" in str(py_file) or "__pycache__" in str(py_file):
                continue
            try:
                content = py_file.read_text(errors='ignore')
                self.file_cache[str(py_file)] = content[:2000]  # храним начало
                tokens = self._tokenize(content)
                for tok in tokens:
                    self.index[tok].add(str(py_file))
            except:
                pass
    
    def search(self, query, top_n=5):
        tokens = self._tokenize(query)
        scores = defaultdict(int)
        for tok in tokens:
            for file in self.index.get(tok, []):
                scores[file] += 1
        sorted_files = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for file, score in sorted_files[:top_n]:
            snippet = self.file_cache.get(file, "")[:200]
            results.append(f"{file} (score={score})\n{snippet}\n")
        return "\n".join(results) if results else "Ничего не найдено"

_index = None  # ленивая инициализация

def search_code(query, directory=".", top_n=5):
    global _index
    if _index is None or str(_index.root_dir) != directory:
        _index = SimpleIndex(directory)
    return _index.search(query, top_n)

TOOLS = {
    "search_code": search_code,
}

def handle_request(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "result": {"tools": [{"name": n} for n in TOOLS]}, "id": rid}
    elif method == "tools/call":
        tool = req.get("params", {}).get("name")
        args = req.get("params", {}).get("arguments", {})
        if tool in TOOLS:
            try:
                res = TOOLS[tool](**args)
                return {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": res}]}, "id": rid}
            except Exception as e:
                return {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": rid}
        else:
            return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unknown {tool}"}, "id": rid}
    else:
        return {"jsonrpc": "2.0", "error": {"code": -32601, "message": f"Unknown method {method}"}, "id": rid}

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
