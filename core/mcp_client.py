import subprocess
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any

BASE_DIR = Path.home() / ".xli"
MCP_SCRIPTS_DIR = BASE_DIR / "mcp_servers"
CONFIG_FILE = BASE_DIR / "mcp_config.json"

def load_mcp_config() -> Dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_mcp_config(config: Dict):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

# ТВОИ РЕАЛЬНЫЕ MCP СЕРВЕРЫ (из ls)
POTENTIAL_SERVERS: Dict[str, Dict[str, Any]] = {
    "archaeologist": {
        "script": MCP_SCRIPTS_DIR / "archaeologist_cli.py",
        "tools": ["blame_line", "code_ownership", "commit_history", "temporal_coupling"],
        "description": "История кода, blame, git анализ",
        "enabled": True
    },
    "refactor": {
        "script": MCP_SCRIPTS_DIR / "refactor_cli.py",
        "tools": ["analyze_complexity", "detect_long_methods"],
        "description": "Анализ сложности и рефакторинг",
        "enabled": True
    },
    "architecture": {
        "script": MCP_SCRIPTS_DIR / "architecture_cli.py",
        "tools": ["dependency_graph", "circular_dependencies", "suggest_modules"],
        "description": "Граф зависимостей, архитектура",
        "enabled": True
    },
    "prompt": {
        "script": MCP_SCRIPTS_DIR / "prompt_cli.py",
        "tools": ["prompt_create", "prompt_get", "prompt_list", "prompt_evaluate"],
        "description": "Управление промптами",
        "enabled": True
    },
    "auto_tester": {
        "script": MCP_SCRIPTS_DIR / "mcp-auto-tester-cli.py",
        "tools": ["discover_tests", "run_tests", "fix_test"],
        "description": "Автоматическое тестирование",
        "enabled": True
    },
    "debugger": {
        "script": MCP_SCRIPTS_DIR / "mcp-debugger-cli.py",
        "tools": ["analyze_traceback"],
        "description": "Анализ ошибок и отладка",
        "enabled": True
    },
    "knowledge_base": {
        "script": MCP_SCRIPTS_DIR / "mcp-knowledge-cli.py",
        "tools": ["search_code"],
        "description": "Поиск по коду",
        "enabled": True
    },
    "package_monitor": {
        "script": MCP_SCRIPTS_DIR / "mcp-package-monitor-cli.py",
        "tools": ["list_dependencies", "check_vulnerabilities", "update_dependencies"],
        "description": "Мониторинг пакетов",
        "enabled": True
    },
    "shell_helper": {
        "script": MCP_SCRIPTS_DIR / "mcp-shell-helper-cli.py",
        "tools": ["suggest_command", "fix_typo", "generate_complex_command"],
        "description": "Помощник по shell командам",
        "enabled": True
    },
    "refactor_npm": {
        "command": ["npx", "-y", "@myuon/refactor-mcp"],
        "tools": ["code_search", "code_refactor"],
        "description": "Рефакторинг (npm)",
        "enabled": True,
        "is_npx": True
    }
}

_available_servers = None

def get_available_servers() -> Dict[str, Dict[str, Any]]:
    global _available_servers
    if _available_servers is None:
        _available_servers = {}
        for name, info in POTENTIAL_SERVERS.items():
            if not info.get("enabled", True):
                continue
            if info.get("is_npx"):
                try:
                    subprocess.run(["npx", "--version"], capture_output=True, timeout=5)
                    _available_servers[name] = info
                except:
                    pass
            elif info.get("script") and info["script"].exists():
                _available_servers[name] = info
    return _available_servers

def call_mcp_tool(server_name: str, tool_name: str, arguments: dict, timeout: int = 60) -> str:
    servers = get_available_servers()
    if server_name not in servers:
        return f"❌ Сервер '{server_name}' не доступен"

    server = servers[server_name]
    if tool_name not in server.get("tools", []):
        return f"❌ Инструмент '{tool_name}' не найден"

    request = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": 1
    }

    try:
        if server.get("is_npx"):
            cmd = server["command"]
        else:
            cmd = [sys.executable, str(server["script"])]
        
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(json.dumps(request), timeout=timeout)

        if stderr:
            return f"⚠️ {stderr[:200]}"

        resp = json.loads(stdout)
        if "result" in resp:
            content = resp["result"].get("content", [])
            if content and "text" in content[0]:
                return content[0]["text"]
            return str(resp["result"])
        elif "error" in resp:
            return f"❌ {resp['error'].get('message', 'unknown')}"
        else:
            return f"⚠️ Неизвестный ответ"

    except subprocess.TimeoutExpired:
        proc.kill()
        return "❌ Таймаут"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def process_mcp_tags(text: str) -> str:
    """Удаляет MCP теги (пока отключено)"""
    pattern = r'<mcp:\w+_\w+>.*?</mcp:\w+_\w+>'
    return re.sub(pattern, '', text, flags=re.DOTALL)

def list_mcp_servers() -> Dict:
    result = {}
    for name, info in POTENTIAL_SERVERS.items():
        result[name] = {
            "enabled": info.get("enabled", True),
            "available": name in get_available_servers(),
            "description": info["description"]
        }
    return result

def toggle_mcp_server(server_name: str, enabled: bool) -> bool:
    if server_name not in POTENTIAL_SERVERS:
        return False
    POTENTIAL_SERVERS[server_name]["enabled"] = enabled
    config = load_mcp_config()
    config[server_name] = {"enabled": enabled}
    save_mcp_config(config)
    global _available_servers
    _available_servers = None
    return True
