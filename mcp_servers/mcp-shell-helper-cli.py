#!/usr/bin/env python3
# mcp-shell-helper-cli.py — умный автодополнитель команд
import json
import sys
import subprocess
from pathlib import Path
from difflib import get_close_matches

HISTORY_FILE = Path.home() / ".zsh_history"
if not HISTORY_FILE.exists():
    HISTORY_FILE = Path.home() / ".bash_history"

def load_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        text = HISTORY_FILE.read_text(errors='ignore')
        lines = []
        for line in text.split('\n'):
            if ';' in line:
                parts = line.split(';', 1)
                if len(parts) == 2:
                    lines.append(parts[1].strip())
            else:
                lines.append(line.strip())
        return [l for l in lines if l and not l.startswith('#')][-200:]
    except:
        return []

def suggest_command(partial):
    """Поиск похожих команд в истории"""
    history = load_history()
    matches = get_close_matches(partial, history, n=5, cutoff=0.4)
    if matches:
        return "Предлагаю:\n" + "\n".join(f"  {m}" for m in matches)
    return "Нет похожих команд"

def fix_typo(command):
    """Исправление очевидных опечаток"""
    fixes = {
        "gti": "git", "got": "git", "pythn": "python",
        "pip3": "pip", "cdd": "cd", "ls -al": "ls -la"
    }
    cmd_lower = command.lower()
    for wrong, correct in fixes.items():
        if cmd_lower.startswith(wrong):
            return command.replace(wrong, correct, 1)
    return command

def generate_complex_command(description):
    """Генерация сложной команды по описанию (заглушка)"""
    return f"Для '{description}' сгенерируйте команду с помощью agent"

TOOLS = {
    "suggest_command": suggest_command,
    "fix_typo": fix_typo,
    "generate_complex_command": generate_complex_command,
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
