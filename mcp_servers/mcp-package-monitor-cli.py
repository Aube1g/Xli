#!/usr/bin/env python3
# mcp-package-monitor-cli.py — проверка зависимостей
import json
import sys
import subprocess
from pathlib import Path

def list_dependencies():
    """Список всех пакетов из requirements.txt / pyproject.toml"""
    deps = []
    req_file = Path("requirements.txt")
    if req_file.exists():
        with open(req_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    deps.append(line)
    else:
        try:
            result = subprocess.run(["pip", "freeze"], capture_output=True, text=True)
            deps = result.stdout.strip().split('\n')
        except:
            pass
    return "\n".join(deps[:20]) if deps else "Не удалось определить зависимости"

def check_vulnerabilities():
    """Проверка уязвимостей через safety (если установлен)"""
    try:
        result = subprocess.run(["safety", "check", "--json"], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return "✅ Уязвимостей не найдено"
        else:
            return f"⚠️ Найдены уязвимости:\n{result.stdout[:500]}"
    except FileNotFoundError:
        return "safety не установлен. Установите: pip install safety"
    except subprocess.TimeoutExpired:
        return "Таймаут проверки"

def update_dependencies(dry_run=True):
    """Предложение обновить пакеты (заглушка)"""
    return "Для обновления выполните: pip install --upgrade \n" if not dry_run else "Проверка обновлений: pip list --outdated"

TOOLS = {
    "list_dependencies": list_dependencies,
    "check_vulnerabilities": check_vulnerabilities,
    "update_dependencies": update_dependencies,
}

# --- стандартный обработчик ---
def handle_request(req):
    method = req.get("method")
    rid = req.get("id")
    if method == "tools/list":
        return {"jsonrpc":"2.0","result":{"tools":[{"name":n} for n in TOOLS]},"id":rid}
    elif method == "tools/call":
        tool = req.get("params",{}).get("name")
        args = req.get("params",{}).get("arguments",{})
        if tool in TOOLS:
            try:
                res = TOOLS[tool](**args)
                return {"jsonrpc":"2.0","result":{"content":[{"type":"text","text":res}]},"id":rid}
            except Exception as e:
                return {"jsonrpc":"2.0","error":{"code":-32000,"message":str(e)},"id":rid}
        return {"jsonrpc":"2.0","error":{"code":-32601,"message":f"Unknown {tool}"},"id":rid}
    return {"jsonrpc":"2.0","error":{"code":-32601,"message":f"Unknown method {method}"},"id":rid}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        try:
            req = json.loads(line)
            resp = handle_request(req)
            print(json.dumps(resp), flush=True)
        except Exception as e:
            print(json.dumps({"jsonrpc":"2.0","error":{"code":-32700,"message":str(e)}}), flush=True)

if __name__ == "__main__":
    main()
