#!/usr/bin/env python3
# mcp-architecture-cli.py — анализ зависимостей и циклов
import json
import sys
import subprocess
from pathlib import Path

def dependency_graph(directory="."):
    """Построить граф импортов в JSON"""
    imports = {}
    for py_file in Path(directory).rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue
        name = str(py_file)
        deps = []
        try:
            with open(py_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("import "):
                        deps.append(line.split()[1])
                    elif line.startswith("from "):
                        parts = line.split()
                        if len(parts) >= 2:
                            deps.append(parts[1])
        except:
            pass
        if deps:
            imports[name] = deps
    return json.dumps(imports, indent=2)

def circular_dependencies(directory="."):
    """Поиск циклических импортов (упрощённо)"""
    # Простая эвристика
    imports = {}
    for py_file in Path(directory).rglob("*.py"):
        if any(x in str(py_file) for x in ["venv","__pycache__"]):
            continue
        name = str(py_file)
        deps = []
        try:
            with open(py_file) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("import "):
                        deps.append(line.split()[1])
                    elif line.startswith("from "):
                        parts = line.split()
                        if len(parts) >= 2:
                            deps.append(parts[1])
        except:
            pass
        imports[name] = deps

    # поиск циклов (A->B, B->A)
    cycles = []
    for a, deps in imports.items():
        for b in deps:
            if b in imports and a in imports.get(b, []):
                cycles.append((a, b))
    return json.dumps(cycles, indent=2) if cycles else "Циклов не обнаружено"

def suggest_modules(directory=".", clusters=3):
    """Предложить разбиение на модули (по центральности импортов)"""
    # Простейшая реализация: собрать все файлы
    files = [str(p) for p in Path(directory).rglob("*.py") if "venv" not in str(p) and "__pycache__" not in str(p)]
    if not files:
        return "Нет Python файлов"
    total = len(files)
    chunk = max(1, total // clusters)
    suggestions = [files[i:i+chunk] for i in range(0, total, chunk)]
    result = f"Предлагаемое разбиение на {clusters} модулей:\n"
    for i, group in enumerate(suggestions):
        result += f"Модуль {i+1}: {len(group)} файлов, примеры: {', '.join(group[:2])}\n"
    return result

TOOLS = {
    "dependency_graph": dependency_graph,
    "circular_dependencies": circular_dependencies,
    "suggest_modules": suggest_modules,
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
                res = TOOLS[tool](**args)
                return {
                    "jsonrpc": "2.0",
                    "result": {"content": [{"type": "text", "text": res}]},
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
