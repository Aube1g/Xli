import subprocess
import os
from pathlib import Path

def run_python_file(filepath: str, args: list = None) -> str:
    """Безопасный запуск Python файла"""
    path = Path(filepath).expanduser()
    if not path.exists():
        return f"❌ Файл не найден: {filepath}"
    
    cmd = ["python3", str(path)]
    if args:
        cmd.extend(args)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=path.parent)
        if result.returncode == 0:
            return f"✅ Выполнено:\n{result.stdout[:500]}"
        else:
            return f"❌ Ошибка:\n{result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "❌ Таймаут выполнения"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def run_shell_script(filepath: str, args: list = None) -> str:
    """Запуск shell скрипта"""
    path = Path(filepath).expanduser()
    if not path.exists():
        return f"❌ Файл не найден: {filepath}"
    
    os.chmod(path, 0o755)
    
    cmd = [str(path)]
    if args:
        cmd.extend(args)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=path.parent)
        if result.returncode == 0:
            return f"✅ Выполнено:\n{result.stdout[:500]}"
        else:
            return f"❌ Ошибка:\n{result.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "❌ Таймаут"
    except Exception as e:
        return f"❌ Ошибка: {e}"

def detect_and_run(filepath: str, args: list = None) -> str:
    """Автоопределение типа файла и запуск"""
    path = Path(filepath)
    if path.suffix == '.py':
        return run_python_file(filepath, args)
    elif path.suffix in ['.sh', '.bash']:
        return run_shell_script(filepath, args)
    else:
        # Попытка запустить как исполняемый
        try:
            return run_shell_script(filepath, args)
        except:
            return f"❌ Неизвестный тип файла: {path.suffix}"
