#!/usr/bin/env python3
"""
XLI Environment Adapter v2
Определяет среду выполнения и адаптирует команды
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass, field


@dataclass
class Environment:
    """Контекст выполнения"""
    name: str                          # "terminal", "neovim", "headless"
    shell: str
    cwd: str
    home: str
    is_termux: bool = False
    has_textual: bool = False
    has_pynvim: bool = False
    nvim_listen: Optional[str] = None

    # Neovim callbacks (устанавливаются при инициализации)
    _nvim_notify: Optional[Callable] = None
    _nvim_cmd: Optional[Callable] = None
    _nvim_buf: Optional[Callable] = None
    _nvim_float: Optional[Callable] = None


class EnvironmentAdapter:
    """Адаптирует операции под текущую среду"""

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

    def _detect(self) -> Environment:
        """Автоопределение среды"""
        home = str(Path.home())
        cwd = os.getcwd()
        shell = os.environ.get('SHELL', '/bin/bash')
        is_termux = '/data/data/com.termux' in home

        # Проверяем textual
        has_textual = False
        try:
            import textual
            has_textual = True
        except ImportError:
            pass

        # Проверяем Neovim RPC
        has_pynvim = False
        nvim_listen = None
        try:
            import pynvim
            has_pynvim = True
            nvim_listen = os.environ.get('NVIM_LISTEN_ADDRESS')
            if not nvim_listen and 'NVIM' in os.environ:
                # Внутри :terminal в Neovim
                nvim_listen = os.environ.get('NVIM', '')
        except ImportError:
            pass

        # Определяем режим
        if has_pynvim and nvim_listen:
            name = "neovim"
        elif has_textual:
            name = "terminal"
        else:
            name = "headless"

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
        """Настройка логирования"""
        import logging
        log_dir = Path(self.env.home) / ".xli" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger("xli.env")
        self.logger.setLevel(logging.DEBUG)

        # Очищаем старые хендлеры
        self.logger.handlers.clear()

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%H:%M:%S"
        )

        # Файл: все логи
        file_handler = logging.FileHandler(
            log_dir / "xli.log", encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        # Файл: только ошибки
        error_handler = logging.FileHandler(
            log_dir / "errors.log", encoding="utf-8"
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        self.logger.addHandler(error_handler)

        # Консоль только если не в Neovim
        if self.env.name != "neovim":
            console = logging.StreamHandler(sys.stdout)
            console.setLevel(logging.INFO)
            console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self.logger.addHandler(console)

    # ─── Neovim Integration ───

    def set_nvim_callbacks(self, notify=None, cmd=None, buf=None, float_win=None):
        """Устанавливает Neovim callbacks"""
        self.env._nvim_notify = notify
        self.env._nvim_cmd = cmd
        self.env._nvim_buf = buf
        self.env._nvim_float = float_win

    def _nvim_call(self, method: str, *args) -> Any:
        """Вызывает Neovim метод если доступен"""
        callbacks = {
            'notify': self.env._nvim_notify,
            'cmd': self.env._nvim_cmd,
            'buf': self.env._nvim_buf,
            'float': self.env._nvim_float,
        }
        cb = callbacks.get(method)
        if cb:
            try:
                return cb(*args)
            except Exception as e:
                self.logger.error(f"Neovim {method} failed: {e}")
        return None

    # ─── Shell Commands ───

    def run_shell(self, cmd: str, timeout: int = 30) -> str:
        """Выполняет команду адаптивно"""
        self.logger.info(f"Shell: {cmd[:80]}")

        if self.env.name == "neovim":
            # Пробуем через Neovim jobstart
            result = self._nvim_call('cmd', cmd)
            if result:
                return result

        # Fallback: прямой запуск
        return self._run_direct(cmd, timeout)

    def _run_direct(self, cmd: str, timeout: int) -> str:
        import subprocess
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=timeout, cwd=self.env.cwd
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            if result.returncode == 0:
                return f"✅ exit {result.returncode}\n{stdout}" if stdout else f"✅ exit {result.returncode}"
            return f"❌ exit {result.returncode}\n{stderr or stdout}"
        except subprocess.TimeoutExpired:
            return "❌ Таймаут выполнения команды"
        except Exception as e:
            self.logger.exception("Shell execution failed")
            return f"❌ Ошибка: {e}"

    # ─── File Operations ───

    def write_file(self, path: str, content: str) -> str:
        """Создаёт файл адаптивно"""
        self.logger.info(f"Write file: {path}")

        if self.env.name == "neovim":
            result = self._nvim_call('cmd', f'call writefile({json.dumps(content.split(chr(10)))}, "{path}")')
            if result is not None:
                return f"✅ Файл создан (nvim): {path}"

        # Fallback
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            return f"✅ Файл создан: {path}"
        except Exception as e:
            self.logger.exception("File write failed")
            return f"❌ Ошибка создания файла: {e}"

    def read_file(self, path: str) -> str:
        """Читает файл"""
        try:
            return Path(path).read_text(encoding='utf-8')
        except Exception as e:
            self.logger.error(f"File read failed: {e}")
            return f"❌ Ошибка чтения: {e}"

    # ─── Notifications ───

    def notify(self, msg: str, level: str = "info"):
        """Уведомление адаптивно"""
        self.logger.info(f"Notify [{level}]: {msg[:100]}")

        if self.env.name == "neovim":
            result = self._nvim_call('notify', msg, level)
            if result:
                return

        # Fallback
        print(f"[{level.upper()}] {msg}")

    # ─── UI: Buffer & Float ───

    def open_buffer(self, content: List[str], name: str = "XLI Result", 
                    filetype: str = "markdown", float_win: bool = False):
        """Открывает буфер или float window"""
        self.logger.info(f"Open buffer: {name} (float={float_win})")

        if self.env.name == "neovim":
            if float_win and self.env._nvim_float:
                return self._nvim_call('float', content, name, filetype)
            elif self.env._nvim_buf:
                return self._nvim_call('buf', content, name, filetype)

        # Fallback: просто вывод
        print(f"\n=== {name} ===")
        print("\n".join(content))

    # ─── History ───

    def append_history(self, task: str, result: str = "", agent: str = ""):
        """Добавляет в историю"""
        hist_file = Path(self.env.home) / ".xli" / "history.txt"
        hist_file.parent.mkdir(parents=True, exist_ok=True)

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"[{timestamp}] [{agent}] {task}"
        if result:
            entry += f"\n  → {result[:200]}"

        with open(hist_file, 'a', encoding='utf-8') as f:
            f.write(entry + "\n")

        self.logger.debug(f"History appended: {task[:50]}")

    def get_history(self, lines: int = 50) -> List[str]:
        """Читает историю"""
        hist_file = Path(self.env.home) / ".xli" / "history.txt"
        if not hist_file.exists():
            return []

        with open(hist_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            return [l.strip() for l in all_lines[-lines:] if l.strip()]

    # ─── Context for Agents ───

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
            lines.append("- Для создания файлов: <SHELL>echo '...' > /full/path</SHELL>")
            lines.append("- Для выполнения: shell команды через <SHELL>")
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
            lines.append(f"  {'✅' if available else '❌'} {tool}")

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


def get_env() -> EnvironmentAdapter:
    """Получить глобальный адаптер"""
    return EnvironmentAdapter()
