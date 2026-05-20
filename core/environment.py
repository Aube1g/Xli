#!/usr/bin/env python3
"""
XLI Environment Adapter v3
Определяет среду выполнения и адаптирует команды
Добавлено: structured logging, error tracking, nvim error capture
"""

import os
import sys
import json
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Environment:
    """Контекст выполнения"""
    name: str
    shell: str
    cwd: str
    home: str
    is_termux: bool = False
    has_textual: bool = False
    has_pynvim: bool = False
    nvim_listen: Optional[str] = None

    _nvim_notify: Optional[Callable] = None
    _nvim_cmd: Optional[Callable] = None
    _nvim_buf: Optional[Callable] = None
    _nvim_float: Optional[Callable] = None


class StructuredLogEntry:
    """Структурированная запись лога"""
    def __init__(self, level: str, component: str, message: str, 
                 details: Optional[Dict] = None, exc_info: Optional[str] = None):
        self.timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.level = level
        self.component = component
        self.message = message
        self.details = details or {}
        self.exc_info = exc_info

    def to_line(self) -> str:
        base = f"[{self.timestamp}] [{self.level:>5}] [{self.component}] {self.message}"
        if self.details:
            base += f" | details={json.dumps(self.details, ensure_ascii=False, default=str)}"
        if self.exc_info:
            base += f"\n[TRACE] {self.exc_info}"
        return base


class EnvironmentAdapter:
    """Адаптирует операции под текущую среду с полным логированием"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.env = self._detect()
        self._setup_logger()
        self._error_count = 0
        self._setup_global_exception_hook()
        self.logger.info(f"Environment initialized: {self.env.name}")

    def _setup_global_exception_hook(self):
        """Перехват необработанных исключений"""
        original_hook = sys.excepthook

        def custom_hook(exc_type, exc_value, exc_traceback):
            self._log_structured("CRITICAL", "uncaught", 
                f"Uncaught exception: {exc_type.__name__}: {exc_value}",
                exc_info="".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            original_hook(exc_type, exc_value, exc_traceback)

        sys.excepthook = custom_hook

    def _detect(self) -> Environment:
        """Автоопределение среды с логированием"""
        home = str(Path.home())
        cwd = os.getcwd()
        shell = os.environ.get('SHELL', '/bin/bash')
        is_termux = '/data/data/com.termux' in home

        self._log_structured("DEBUG", "env_detect", "Starting environment detection")

        has_textual = False
        try:
            import textual
            has_textual = True
            self._log_structured("DEBUG", "env_detect", "textual available")
        except ImportError:
            self._log_structured("DEBUG", "env_detect", "textual not available")

        has_pynvim = False
        nvim_listen = None
        try:
            import pynvim
            has_pynvim = True
            nvim_listen = os.environ.get('NVIM_LISTEN_ADDRESS')
            if not nvim_listen and 'NVIM' in os.environ:
                nvim_listen = os.environ.get('NVIM', '')
            self._log_structured("DEBUG", "env_detect", f"pynvim available, listen={nvim_listen}")
        except ImportError as e:
            self._log_structured("DEBUG", "env_detect", f"pynvim not available: {e}")

        if has_pynvim and nvim_listen:
            name = "neovim"
        elif has_textual:
            name = "terminal"
        else:
            name = "headless"

        self._log_structured("INFO", "env_detect", f"Detected mode: {name}")

        return Environment(
            name=name,
            shell=shell,
            cwd=cwd,
            home=home,
            is_termux=is_termux,
            has_textual=has_textual,
            has_pynvim=has_pynvim,
            nvim_listen=nvim_listen,
        )

    def _setup_logger(self):
        """Настройка структурированного логирования"""
        self.log_dir = Path(self.env.home) / ".xli" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        import logging
        self.logger = logging.getLogger("xli.env")
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%H:%M:%S"
        )

        file_handler = logging.FileHandler(
            self.log_dir / "xli.log", encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        error_handler = logging.FileHandler(
            self.log_dir / "errors.log", encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)

        self.structured_log_path = self.log_dir / "structured.log"

        if self.env.name != "neovim":
            console = logging.StreamHandler(sys.stdout)
            console.setLevel(logging.INFO)
            console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self.logger.addHandler(console)

    def _log_structured(self, level: str, component: str, message: str, 
                       details: Optional[Dict] = None, exc_info: Optional[str] = None):
        """Записывает структурированный лог"""
        entry = StructuredLogEntry(level, component, message, details, exc_info)
        try:
            with open(self.structured_log_path, 'a', encoding='utf-8') as f:
                f.write(entry.to_line() + "\n")
        except Exception as e:
            self.logger.error(f"Failed to write structured log: {e}")

        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(f"[{component}] {message}")

    def log_error(self, component: str, message: str, exc: Optional[Exception] = None,
                  details: Optional[Dict] = None):
        """Унифицированное логирование ошибок"""
        self._error_count += 1
        exc_str = None
        if exc:
            exc_str = traceback.format_exc()
        self._log_structured("ERROR", component, message, details, exc_str)
        self.logger.error(f"[{component}] {message}", exc_info=exc is not None)

    def log_nvim_error(self, source: str, message: str, details: Optional[Dict] = None):
        """Логирует ошибку от Neovim Lua стороны"""
        self._log_structured("ERROR", f"nvim.{source}", message, details)
        nvim_err_file = self.log_dir / "nvim_errors.log"
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{source}] {message}"
        if details:
            line += f" | {json.dumps(details, ensure_ascii=False, default=str)}"
        try:
            with open(nvim_err_file, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
        except Exception as e:
            self.logger.error(f"Failed to write nvim error log: {e}")

    def set_nvim_callbacks(self, notify=None, cmd=None, buf=None, float_win=None):
        """Устанавливает Neovim callbacks"""
        self.env._nvim_notify = notify
        self.env._nvim_cmd = cmd
        self.env._nvim_buf = buf
        self.env._nvim_float = float_win
        self._log_structured("DEBUG", "nvim", "Callbacks registered")

    def _nvim_call(self, method: str, *args) -> Any:
        """Вызывает Neovim метод если доступен с логированием"""
        callbacks = {
            'notify': self.env._nvim_notify,
            'cmd': self.env._nvim_cmd,
            'buf': self.env._nvim_buf,
            'float': self.env._nvim_float,
        }
        cb = callbacks.get(method)
        if cb:
            try:
                result = cb(*args)
                self._log_structured("DEBUG", "nvim.call", f"Method {method} succeeded")
                return result
            except Exception as e:
                self.log_error("nvim.call", f"Method {method} failed: {e}", exc=e,
                               details={"method": method, "args_count": len(args)})
                return None
        else:
            self._log_structured("DEBUG", "nvim.call", f"Callback {method} not set")
        return None

    def run_shell(self, cmd: str, timeout: int = 30) -> str:
        """Выполняет команду адаптивно с полным логированием"""
        self._log_structured("INFO", "shell", f"Executing: {cmd[:100]}", 
                             details={"timeout": timeout, "cwd": self.env.cwd})

        if self.env.name == "neovim":
            result = self._nvim_call('cmd', cmd)
            if result is not None:
                self._log_structured("DEBUG", "shell", "Executed via nvim cmd callback")
                return result
            self._log_structured("WARN", "shell", "Nvim cmd callback failed, falling back")

        return self._run_direct(cmd, timeout)

    def _run_direct(self, cmd: str, timeout: int) -> str:
        """Прямой запуск с логированием stdout/stderr"""
        import subprocess
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=timeout, cwd=self.env.cwd
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            self._log_structured("DEBUG", "shell", f"Exit code: {result.returncode}",
                                 details={
                                     "stdout_len": len(stdout),
                                     "stderr_len": len(stderr),
                                     "cmd": cmd[:80]
                                 })

            if result.returncode == 0:
                return f"✅ exit {result.returncode}\n{stdout}" if stdout else f"✅ exit {result.returncode}"

            self.log_error("shell", f"Command failed with exit code {result.returncode}",
                           details={"cmd": cmd[:100], "stderr": stderr[:500], "stdout": stdout[:500]})
            return f"❌ exit {result.returncode}\n{stderr or stdout}"

        except subprocess.TimeoutExpired:
            self.log_error("shell", f"Command timeout after {timeout}s", 
                           details={"cmd": cmd[:100]})
            return "❌ Таймаут выполнения команды"
        except Exception as e:
            self.log_error("shell", f"Command execution failed: {e}", exc=e,
                           details={"cmd": cmd[:100]})
            return f"❌ Ошибка: {e}"

    def write_file(self, path: str, content: str) -> str:
        """Создаёт файл адаптивно с логированием"""
        self._log_structured("INFO", "file", f"Writing file: {path}",
                             details={"content_len": len(content)})

        if self.env.name == "neovim":
            result = self._nvim_call('cmd', 
                f'call writefile({json.dumps(content.split(chr(10)))}, "{path}")')
            if result is not None:
                return f"✅ Файл создан (nvim): {path}"

        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            self._log_structured("INFO", "file", f"File written: {path}")
            return f"✅ Файл создан: {path}"
        except Exception as e:
            self.log_error("file", f"Failed to write {path}: {e}", exc=e)
            return f"❌ Ошибка создания файла: {e}"

    def read_file(self, path: str) -> str:
        """Читает файл с логированием"""
        try:
            content = Path(path).read_text(encoding='utf-8')
            self._log_structured("DEBUG", "file", f"Read file: {path}",
                                 details={"content_len": len(content)})
            return content
        except Exception as e:
            self.log_error("file", f"Failed to read {path}: {e}", exc=e)
            return f"❌ Ошибка чтения: {e}"

    def notify(self, msg: str, level: str = "info"):
        """Уведомление адаптивно с логированием"""
        self._log_structured("INFO", "notify", f"Notify [{level}]: {msg[:100]}")

        if self.env.name == "neovim":
            result = self._nvim_call('notify', msg, level)
            if result:
                return

        print(f"[{level.upper()}] {msg}")

    def open_buffer(self, content: List[str], name: str = "XLI Result",
                    filetype: str = "markdown", float_win: bool = False):
        """Открывает буфер или float window с логированием"""
        self._log_structured("INFO", "ui", f"Open buffer: {name} (float={float_win})")

        if self.env.name == "neovim":
            if float_win and self.env._nvim_float:
                result = self._nvim_call('float', content, name, filetype)
                if result:
                    return result
            elif self.env._nvim_buf:
                result = self._nvim_call('buf', content, name, filetype)
                if result:
                    return result
            self._log_structured("WARN", "ui", "Nvim UI callbacks failed, falling back to print")

        print(f"\n=== {name} ===")
        print("\n".join(content))

    def append_history(self, task: str, result: str = "", agent: str = ""):
        """Добавляет в историю с логированием"""
        hist_file = Path(self.env.home) / ".xli" / "history.txt"
        hist_file.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] [{agent}] {task}"
        if result:
            entry += f"\n → {result[:200]}"

        try:
            with open(hist_file, 'a', encoding='utf-8') as f:
                f.write(entry + "\n")
            self._log_structured("DEBUG", "history", f"Appended: {task[:50]}")
        except Exception as e:
            self.log_error("history", f"Failed to append history: {e}", exc=e)

    def get_history(self, lines: int = 50) -> List[str]:
        """Читает историю с логированием"""
        hist_file = Path(self.env.home) / ".xli" / "history.txt"
        if not hist_file.exists():
            return []

        try:
            with open(hist_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            result = [l.strip() for l in all_lines[-lines:] if l.strip()]
            self._log_structured("DEBUG", "history", f"Read {len(result)} lines")
            return result
        except Exception as e:
            self.log_error("history", f"Failed to read history: {e}", exc=e)
            return []

    def get_system_prompt_addon(self) -> str:
        """Дополнительный контекст для промпта агента"""
        lines = ["\n🎯 КОНТЕКСТ ВЫПОЛНЕНИЯ:"]
        lines.append(f"- Среда: {self.env.name.upper()}")
        lines.append(f"- Текущая директория: {self.env.cwd}")
        lines.append(f"- Домашняя: {self.env.home}")

        if self.env.is_termux:
            lines.append("- Платформа: Termux (Android)")
            lines.append("- Пакетный менеджер: pkg")
            lines.append("- Python: python3")
            lines.append("- Node: node, npm")
            lines.append("- Storage: ~/storage/ для доступа к Android")

        if self.env.name == "neovim":
            lines.append("\n📋 NEOVIM MODE:")
            lines.append("- НЕ используй textual/tui команды")
            lines.append("- Для создания файлов: echo '...' > /full/path")
            lines.append("- Для выполнения: shell команды через ")
            lines.append("- Результат возвращай как текст, Neovim отобразит в буфере")
            lines.append("- Можешь использовать nvim API через специальные токены")
        elif self.env.name == "terminal":
            lines.append("\n📋 TERMINAL MODE:")
            lines.append("- Можешь использовать полный TUI")
            lines.append("- Доступен textual для интерфейса")
        else:
            lines.append("\n📋 HEADLESS MODE:")
            lines.append("- Только текстовый вывод")
            lines.append("- Нет интерактивного UI")

        lines.append("\n🔧 ДОСТУПНЫЕ ИНСТРУМЕНТЫ:")
        for tool, available in self.get_available_tools().items():
            lines.append(f" {'✅' if available else '❌'} {tool}")

        return "\n".join(lines)

    def get_available_tools(self) -> Dict[str, bool]:
        """Возвращает доступные инструменты"""
        return {
            "shell": True,
            "file_write": True,
            "file_read": True,
            "nvim_api": self.env.name == "neovim",
            "nvim_float": self.env.name == "neovim" and self.env._nvim_float is not None,
            "mcp": True,
            "skills": True,
            "textual_ui": self.env.has_textual,
        }

    def get_mode(self) -> str:
        """Возвращает текущий режим"""
        return self.env.name

    def get_error_summary(self) -> Dict[str, Any]:
        """Сводка ошибок для диагностики"""
        return {
            "error_count": self._error_count,
            "log_dir": str(self.log_dir),
            "structured_log": str(self.structured_log_path),
            "env": self.env.name,
            "is_termux": self.env.is_termux,
        }


def get_env() -> EnvironmentAdapter:
    """Получить глобальный адаптер"""
    return EnvironmentAdapter()
