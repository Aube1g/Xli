#!/usr/bin/env python3
# mcp-prompt-cli.py — простое версионирование промптов
import json
import sys
import hashlib
from pathlib import Path
from datetime import datetime

STORAGE = Path.home() / ".xli" / "prompts.json"
STORAGE.parent.mkdir(exist_ok=True)

def load_prompts():
    if STORAGE.exists():
        with open(STORAGE) as f:
            return json.load(f)
    return {}

def save_prompts(prompts):
    with open(STORAGE, "w") as f:
        json.dump(prompts, f, indent=2)

def prompt_create(name, template, tags=None):
    prompts = load_prompts()
    version = hashlib.sha256(template.encode()).hexdigest()[:8]
    prompts[name] = {
        "template": template,
        "version": version,
        "tags": tags or [],
        "created": datetime.now().isoformat()
    }
    save_prompts(prompts)
    return f"Промпт '{name}' сохранён, версия {version}"

def prompt_get(name):
    prompts = load_prompts()
    if name not in prompts:
        return f"Промпт '{name}' не найден"
    p = prompts[name]
    return f"Версия: {p['version']}\nТеги: {', '.join(p['tags'])}\n---\n{p['template']}"

def prompt_list(tag=None):
    prompts = load_prompts()
    if tag:
        filtered = {k:v for k,v in prompts.items() if tag in v.get("tags", [])}
    else:
        filtered = prompts
    return "\n".join([f"{k} (v{v['version']})" for k,v in filtered.items()]) or "Нет промптов"

def prompt_evaluate(name, test_cases):
    # имитация оценки — просто возвращаем промпт с подстановкой
    prompts = load_prompts()
    if name not in prompts:
        return f"Промпт '{name}' не найден"
    template = prompts[name]["template"]
    results = []
    for test in test_cases:
        filled = template.replace("{{input}}", test)
        results.append(f"Тест '{test}': {filled[:100]}...")
    return "\n".join(results)

TOOLS = {
    "prompt_create": prompt_create,
    "prompt_get": prompt_get,
    "prompt_list": prompt_list,
    "prompt_evaluate": prompt_evaluate,
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
