#!/usr/bin/env python3
"""
XLI-Neovim RPC Bridge v3
Двусторонняя связь Python ↔ Neovim через msgpack
Добавлено: полное логирование всех операций, error tracking
"""

import os
import sys
import json
import time
import traceback
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable

class NvimBridge:
    """RPC bridge для интеграции с Neovim с логированием"""

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
        self.nvim = None
        self._connected = False
        self._connection_errors = []
        self._setup_logger()
        self._connect()
        self._log_connection_status()

    def _setup_logger(self):
        """Настройка логгера"""
        import logging
        self.logger = logging.getLogger("xli.nvim_bridge")
        self.logger.setLevel(logging.DEBUG)

        if not self.logger.handlers:
            log_dir = Path.home() / ".xli" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)

            fh = logging.FileHandler(log_dir / "nvim_bridge.log", encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
                datefmt="%H:%M:%S"
            ))
            self.logger.addHandler(fh)

    def _log_connection_status(self):
        """Логирует статус подключения"""
        if self._connected:
            self.logger.info(f"NvimBridge connected. Listen: {os.environ.get('NVIM_LISTEN_ADDRESS', 'N/A')}")
        else:
            self.logger.warning("NvimBridge NOT connected")
            if self._connection_errors:
                for err in self._connection_errors[-3:]:
                    self.logger.error(f"Connection error: {err}")

    def _connect(self):
        """Подключение к Neovim с детальным логированием"""
        self.logger.info("Attempting Neovim connection...")

        try:
            import pynvim
            self.logger.debug("pynvim imported successfully")

            # Пробуем socket
            listen_addr = os.environ.get('NVIM_LISTEN_ADDRESS')
            if listen_addr and Path(listen_addr).exists():
                self.logger.info(f"Trying socket: {listen_addr}")
                try:
                    self.nvim = pynvim.attach('socket', path=listen_addr)
                    self._connected = True
                    self.logger.info("Connected via socket")
                    return
                except Exception as e:
                    err_msg = f"Socket connection failed: {e}"
                    self.logger.error(err_msg)
                    self._connection_errors.append(err_msg)

            # Пробуем child (внутри :terminal)
            if 'NVIM' in os.environ:
                self.logger.info("Trying child connection (inside :terminal)")
                try:
                    self.nvim = pynvim.attach('child', argv=sys.argv)
                    self._connected = True
                    self.logger.info("Connected via child")
                    return
                except Exception as e:
                    err_msg = f"Child connection failed: {e}"
                    self.logger.error(err_msg)
                    self._connection_errors.append(err_msg)

            # Пробуем найти сокет
            sock_paths = [
                '/tmp/nvim',
                '/data/data/com.termux/files/usr/tmp/nvim',
                os.path.expanduser('~/.local/share/nvim/server.pipe'),
            ]
            for sock_path in sock_paths:
                if Path(sock_path).exists():
                    self.logger.info(f"Trying socket path: {sock_path}")
                    try:
                        self.nvim = pynvim.attach('socket', path=sock_path)
                        self._connected = True
                        self.logger.info(f"Connected via socket path: {sock_path}")
                        return
                    except Exception as e:
                        err_msg = f"Socket path {sock_path} failed: {e}"
                        self.logger.warning(err_msg)
                        self._connection_errors.append(err_msg)

            self.logger.warning("All connection methods exhausted")

        except ImportError as e:
            err_msg = f"pynvim not installed: {e}"
            self.logger.error(err_msg)
            self._connection_errors.append(err_msg)
        except Exception as e:
            err_msg = f"Unexpected connection error: {e}"
            self.logger.error(err_msg)
            self._connection_errors.append(err_msg)
            traceback.print_exc()

    def is_connected(self) -> bool:
        return self._connected and self.nvim is not None

    def log_operation(self, op: str, status: str, details: Optional[Dict] = None):
        """Унифицированное логирование операций"""
        msg = f"OP[{op}] {status}"
        if details:
            msg += f" | {json.dumps(details, default=str)}"
        if status.startswith("ERROR"):
            self.logger.error(msg)
        elif status.startswith("WARN"):
            self.logger.warning(msg)
        else:
            self.logger.info(msg)

    # ─── Notifications ───

    def notify(self, msg: str, level: str = "info") -> bool:
        """Отправляет vim.notify с логированием"""
        if not self.is_connected():
            self.logger.warning(f"notify() skipped: not connected. Msg: {msg[:50]}")
            return False

        try:
            level_map = {"info": 2, "warn": 3, "warning": 3, "error": 4, "debug": 1}
            nvim_level = level_map.get(level, 2)
            self.nvim.call('vim.notify', msg, nvim_level, {
                'title': '🔥 XLI',
                'timeout': 3000,
            })
            self.log_operation("notify", "OK", {"level": level, "msg_len": len(msg)})
            return True
        except Exception as e:
            self.log_operation("notify", f"ERROR: {e}", {"level": level})
            return False

    # ─── Buffer Operations ───

    def open_buffer(self, content: List[str], name: str = "XLI Result",
                    filetype: str = "markdown", split: str = "vsplit") -> Optional[int]:
        """Открывает буфер с содержимым с логированием"""
        if not self.is_connected():
            self.logger.warning("open_buffer() skipped: not connected")
            return None

        try:
            self.logger.info(f"Creating buffer: {name} (split={split}, lines={len(content)})")

            buf = self.nvim.api.create_buf(False, True)
            buf.name = f"xli://{name}"
            buf.options['filetype'] = filetype
            buf.options['buftype'] = 'nofile'
            buf.options['bufhidden'] = 'hide'

            buf[:] = content
            self.logger.debug(f"Buffer populated: {len(content)} lines")

            self.nvim.command(split)
            win = self.nvim.current.window
            win.buffer = buf

            win.options['wrap'] = True
            win.options['cursorline'] = True

            self.log_operation("open_buffer", "OK", {"bufnr": buf.number, "name": name})
            return buf.number

        except Exception as e:
            self.log_operation("open_buffer", f"ERROR: {e}", {"name": name})
            self.logger.error(traceback.format_exc())
            return None

    def open_float(self, content: List[str], title: str = "XLI",
                   width: int = 80, height: int = 20) -> Optional[int]:
        """Открывает float window с логированием"""
        if not self.is_connected():
            self.logger.warning("open_float() skipped: not connected")
            return None

        try:
            self.logger.info(f"Creating float: {title} ({width}x{height})")

            buf = self.nvim.api.create_buf(False, True)
            buf.options['filetype'] = 'markdown'

            lines = [f" {title} ", "─" * (width - 2)] + content
            buf[:] = lines

            editor_width = self.nvim.options['columns']
            editor_height = self.nvim.options['lines']

            row = (editor_height - height) // 2
            col = (editor_width - width) // 2

            win = self.nvim.api.open_win(buf, True, {
                'relative': 'editor',
                'row': row,
                'col': col,
                'width': width,
                'height': height,
                'style': 'minimal',
                'border': 'rounded',
                'title': f' {title} ',
                'title_pos': 'center',
            })

            self.nvim.api.buf_set_keymap(buf.number, 'n', 'q',
                ':q', {'noremap': True, 'silent': True})

            self.log_operation("open_float", "OK", {"win": win, "title": title})
            return win

        except Exception as e:
            self.log_operation("open_float", f"ERROR: {e}", {"title": title})
            self.logger.error(traceback.format_exc())
            return None

    # ─── Job Operations ───

    def run_job(self, cmd: str, on_stdout: Optional[Callable] = None,
                on_exit: Optional[Callable] = None) -> Optional[int]:
        """Запускает job через jobstart с логированием"""
        if not self.is_connected():
            self.logger.warning("run_job() skipped: not connected")
            return None

        try:
            self.logger.info(f"Starting job: {cmd[:80]}")

            job_id = self.nvim.call('jobstart', cmd, {
                'on_stdout': on_stdout or 'v:lua._xli_job_handler',
                'on_stderr': 'v:lua._xli_job_handler',
                'on_exit': on_exit or 'v:lua._xli_job_exit',
            })

            self.log_operation("run_job", "OK", {"job_id": job_id, "cmd": cmd[:50]})
            return job_id

        except Exception as e:
            self.log_operation("run_job", f"ERROR: {e}", {"cmd": cmd[:50]})
            return None

    def system(self, cmd: str) -> str:
        """Выполняет команду через vim.fn.system с логированием"""
        if not self.is_connected():
            self.logger.warning("system() skipped: not connected")
            return ""

        try:
            self.logger.debug(f"system(): {cmd[:80]}")
            result = self.nvim.call('system', cmd)
            self.log_operation("system", "OK", {"cmd": cmd[:50], "result_len": len(result)})
            return result
        except Exception as e:
            self.log_operation("system", f"ERROR: {e}", {"cmd": cmd[:50]})
            return f"Error: {e}"

    # ─── Context Queries ───

    def get_cwd(self) -> str:
        """Текущая директория Neovim с логированием"""
        if not self.is_connected():
            self.logger.debug("get_cwd() fallback to os.getcwd()")
            return os.getcwd()

        try:
            cwd = self.nvim.call('getcwd')
            self.logger.debug(f"get_cwd(): {cwd}")
            return cwd
        except Exception as e:
            self.logger.error(f"get_cwd() error: {e}")
            return os.getcwd()

    def get_current_file(self) -> str:
        """Путь текущего файла с логированием"""
        if not self.is_connected():
            return ""

        try:
            path = self.nvim.current.buffer.name
            self.logger.debug(f"get_current_file(): {path}")
            return path
        except Exception as e:
            self.logger.error(f"get_current_file() error: {e}")
            return ""

    def get_selection(self) -> str:
        """Получает выделенный текст с логированием"""
        if not self.is_connected():
            return ""

        try:
            old_reg = self.nvim.call('getreg', '"')
            old_regtype = self.nvim.call('getregtype', '"')

            self.nvim.command('normal! gv"xy')
            selection = self.nvim.call('getreg', 'x')

            self.nvim.call('setreg', '"', old_reg, old_regtype)

            self.logger.debug(f"get_selection(): {len(selection)} chars")
            return selection

        except Exception as e:
            self.logger.error(f"get_selection() error: {e}")
            return ""

    def get_buffer_content(self, bufnr: Optional[int] = None) -> List[str]:
        """Содержимое буфера с логированием"""
        if not self.is_connected():
            return []

        try:
            if bufnr:
                buf = self.nvim.buffers[bufnr]
            else:
                buf = self.nvim.current.buffer
            content = buf[:]
            self.logger.debug(f"get_buffer_content({bufnr}): {len(content)} lines")
            return content
        except Exception as e:
            self.logger.error(f"get_buffer_content({bufnr}) error: {e}")
            return []

    # ─── Questionnaire ───

    def open_questionnaire(self, questions: List[Dict[str, Any]],
                           on_complete: Callable[[Dict[str, str]], None]) -> Optional[int]:
        """Открывает интерактивный буфер с вопросами с логированием"""
        if not self.is_connected():
            self.logger.warning("open_questionnaire() skipped: not connected")
            return None

        try:
            self.logger.info(f"Opening questionnaire: {len(questions)} questions")

            buf = self.nvim.api.create_buf(False, True)
            buf.name = "xli://questionnaire"
            buf.options['filetype'] = 'xli_questionnaire'
            buf.options['buftype'] = 'prompt'

            lines = [
                " 🔥 XLI PRO — Уточнение задачи ",
                "─" * 60,
                "",
                "Пожалуйста, ответьте на вопросы для уточнения:",
                "",
            ]

            buf[:] = lines
            self.nvim.command('split')
            win = self.nvim.current.window
            win.buffer = buf
            win.height = min(20, len(lines) + 10)

            self.log_operation("questionnaire", "OK", {"bufnr": buf.number, "questions": len(questions)})
            return buf.number

        except Exception as e:
            self.log_operation("questionnaire", f"ERROR: {e}")
            self.logger.error(traceback.format_exc())
            return None

    # ─── Callbacks for EnvironmentAdapter ───

    def get_callbacks(self) -> Dict[str, Callable]:
        """Возвращает callbacks для EnvironmentAdapter"""
        return {
            'notify': self.notify,
            'cmd': self.system,
            'buf': self.open_buffer,
            'float': self.open_float,
            'job': self.run_job,
        }

    def get_connection_log(self) -> List[str]:
        """Возвращает лог подключения для диагностики"""
        return self._connection_errors


def get_nvim_bridge() -> NvimBridge:
    """Получить bridge"""
    return NvimBridge()
