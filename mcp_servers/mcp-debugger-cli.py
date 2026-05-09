#!/usr/bin/env python3
# mcp-debugger-cli.py — анализ traceback
import json
import sys
import re

def analyze_traceback(traceback_text):
    """Анализирует traceback и предлагает исправления"""
    lines = traceback_text.split('\n')
    error_line = ""
    error_type = "Unknown"
    file_name = ""
    line_no = ""
    
    for line in lines:
        if "File \"" in line and ".py" in line:
            parts = re.findall(r'File "([^"]+)"', line)
            if parts:
                file_name = parts[0]
            nums = re.findall(r'line (\d+)', line)
            if nums:
                line_no = nums[0]
        if "Error:" in line or "Exception:" in line:
            error_line = line
            error_type = line.split(':')[0] if ':' in line else line
    
    suggestions = []
    if "ModuleNotFoundError" in error_type:
        module = re.search(r"No module named '(\w+)'", error_line)
        if module:
            suggestions.append(f"Установи модуль: pip install {module.group(1)}")
    elif "SyntaxError" in error_type:
        suggestions.append("Проверь синтаксис: скобки, кавычки, отступы")
    elif "NameError" in error_type:
        var = re.search(r"name '(\w+)' is not defined", error_line)
        if var:
            suggestions.append(f"Переменная '{var.group(1)}' не определена. Проверь импорт или объявление.")
    elif "TypeError" in error_type:
        suggestions.append("Несоответствие типов. Проверь передаваемые аргументы.")
    elif "FileNotFoundError" in error_type:
        suggestions.append("Файл не найден. Проверь путь.")
    else:
        suggestions.append("Проверь логику в указанном месте.")
    
    result = f"Файл: {file_name}\nСтрока: {line_no}\nОшибка: {error_line}\n\nПредложения:\n" + "\n".join(f"- {s}" for s in suggestions)
    return result

TOOLS = {
    "analyze_traceback": analyze_traceback,
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
