#!/usr/bin/env python3
# mcp-refactor-cli.py — анализ сложности кода (без radon, только базовый)
import json
import sys
import ast
from pathlib import Path

def analyze_complexity(directory, threshold=10):
    results = []
    for py_file in Path(directory).rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue
        try:
            with open(py_file) as f:
                code = f.read()
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # простая оценка: количество узлов в теле
                    complexity = sum(1 for _ in ast.walk(node))
                    if complexity > threshold:
                        results.append(f"{py_file}:{node.lineno} {node.name} (complexity approx {complexity})")
        except:
            pass
    return "\n".join(results[:20]) or "Сложных функций не найдено"

def detect_long_methods(directory, max_lines=50):
    results = []
    for py_file in Path(directory).rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue
        with open(py_file) as f:
            lines = f.readlines()
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith("def "):
                indent = len(lines[i]) - len(lines[i].lstrip())
                j = i+1
                while j < len(lines) and (not lines[j].strip() or (len(lines[j]) - len(lines[j].lstrip())) > indent):
                    j += 1
                func_len = j - i
                if func_len > max_lines:
                    results.append(f"{py_file}:{i+1} длина {func_len} строк")
                i = j
            else:
                i += 1
    return "\n".join(results[:20]) or "Длинных методов не найдено"

TOOLS = {
    "analyze_complexity": analyze_complexity,
    "detect_long_methods": detect_long_methods,
}

def handle_request(request):
    method = request.get("method")
    req_id = request.get("id")
    if method == "tools/list":
        return {"jsonrpc": "2.0", "result": {"tools": [{"name": n} for n in TOOLS.keys()]}, "id": req_id}
    elif method == "tools/call":
        tool = request.get("params", {}).get("name")
        args = request.get("params", {}).get("arguments", {})
        if tool in TOOLS:
            try:
                res = TOOLS[tool](**args)
                return {"jsonrpc": "2.0", "result": {"content": [{"type": "text", "text": res}]}, "id": req_id}
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
