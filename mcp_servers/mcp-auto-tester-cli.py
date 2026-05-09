#!/usr/bin/env python3
# mcp-auto-tester-cli.py — авто-тест-раннер
import json
import sys
import subprocess
from pathlib import Path

def discover_tests(directory="."):
    """Находит все тестовые файлы (test_*.py, *_test.py)"""
    tests = []
    for py_file in Path(directory).rglob("*.py"):
        if "venv" in str(py_file) or "__pycache__" in str(py_file):
            continue
        name = py_file.name
        if name.startswith("test_") or name.endswith("_test.py"):
            tests.append(str(py_file))
    return "\n".join(tests) if tests else "Тестов не найдено"

def run_tests(test_path=None):
    """Запускает pytest и возвращает результат"""
    cmd = ["pytest", "-v", "--tb=short"]
    if test_path:
        cmd.append(test_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        output = result.stdout
        if result.returncode == 0:
            return f"✅ Все тесты пройдены\n{output}"
        else:
            # парсим ошибки
            errors = []
            for line in output.split('\n'):
                if "E " in line or "FAILED" in line or "ERROR" in line:
                    errors.append(line)
            return f"❌ Тесты упали\n{output}\n\nОшибки:\n" + "\n".join(errors[:10])
    except FileNotFoundError:
        return "pytest не установлен. Установите: pip install pytest"
    except subprocess.TimeoutExpired:
        return "Таймаут при выполнении тестов"

def fix_test(test_output):
    """Пытается предложить исправление (заглушка)"""
    return "Предлагаю проверить assert’ы и исключения в коде"

TOOLS = {
    "discover_tests": discover_tests,
    "run_tests": run_tests,
    "fix_test": fix_test,
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

if __name__=="__main__":
    main()
