#!/usr/bin/env python3
"""
XLI-Neovim RPC Bridge v2
Двусторонняя связь Python ↔ Neovim через msgpack
Поддерживает: notify, buffer, float window, jobstart, questionnaire
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable


class NvimBridge:
    """RPC bridge для интеграции с Neovim"""

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
        self._connect()

    def _connect(self):
        """Подключение к Neovim"""
        try:
            import pynvim

            # Пробуем socket
            listen_addr = os.environ.get('NVIM_LISTEN_ADDRESS')
            if listen_addr and Path(listen_addr).exists():
                self.nvim = pynvim.attach('socket', path=listen_addr)
                self._connected = True
                return

            # Пробуем child (внутри :terminal)
            if 'NVIM' in os.environ:
                self.nvim = pynvim.attach('child', argv=sys.argv)
                self._connected = True
                return

            # Пробуем найти сокет
            for sock_path in [
                '/tmp/nvim',
                '/data/data/com.termux/files/usr/tmp/nvim',
                os.path.expanduser('~/.local/share/nvim/server.pipe'),
            ]:
                if Path(sock_path).exists():
                    self.nvim = pynvim.attach('socket', path=sock_path)
                    self._connected = True
                    return

        except ImportError:
            pass
        except Exception as e:
            print(f"⚠️ Neovim connection failed: {e}", file=sys.stderr)

    def is_connected(self) -> bool:
        return self._connected and self.nvim is not None

    # ─── Notifications ───

    def notify(self, msg: str, level: str = "info") -> bool:
        """Отправляет vim.notify"""
        if not self.is_connected():
            return False

        try:
            level_map = {"info": 2, "warn": 3, "warning": 3, "error": 4, "debug": 1}
            self.nvim.call('vim.notify', msg, level_map.get(level, 2), {
                'title': '🔥 XLI',
                'timeout': 3000,
            })
            return True
        except Exception as e:
            print(f"Notify error: {e}", file=sys.stderr)
            return False

    # ─── Buffer Operations ───

    def open_buffer(self, content: List[str], name: str = "XLI Result",
                    filetype: str = "markdown", split: str = "vsplit") -> Optional[int]:
        """Открывает буфер с содержимым"""
        if not self.is_connected():
            return None

        try:
            # Создаём буфер
            buf = self.nvim.api.create_buf(False, True)
            buf.name = f"xli://{name}"
            buf.options['filetype'] = filetype
            buf.options['buftype'] = 'nofile'
            buf.options['bufhidden'] = 'hide'

            # Заполняем содержимым
            buf[:] = content

            # Открываем окно
            self.nvim.command(split)
            win = self.nvim.current.window
            win.buffer = buf

            # Настройки окна
            win.options['wrap'] = True
            win.options['cursorline'] = True

            return buf.number
        except Exception as e:
            print(f"Buffer error: {e}", file=sys.stderr)
            return None

    def open_float(self, content: List[str], title: str = "XLI",
                   width: int = 80, height: int = 20) -> Optional[int]:
        """Открывает float window (если nui.nvim не доступен — fallback)"""
        if not self.is_connected():
            return None

        try:
            # Создаём буфер
            buf = self.nvim.api.create_buf(False, True)
            buf.options['filetype'] = 'markdown'

            # Добавляем заголовок
            lines = [f" {title} ", "─" * (width - 2)] + content
            buf[:] = lines

            # Рассчитываем позицию (центр экрана)
            editor_width = self.nvim.options['columns']
            editor_height = self.nvim.options['lines']

            row = (editor_height - height) // 2
            col = (editor_width - width) // 2

            # Создаём float window
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

            # Клавиша q для закрытия
            self.nvim.api.buf_set_keymap(buf.number, 'n', 'q', 
                ':q<CR>', {'noremap': True, 'silent': True})

            return win
        except Exception as e:
            print(f"Float error: {e}", file=sys.stderr)
            return None

    # ─── Job Operations ───

    def run_job(self, cmd: str, on_stdout: Optional[Callable] = None,
                on_exit: Optional[Callable] = None) -> Optional[int]:
        """Запускает job через jobstart"""
        if not self.is_connected():
            return None

        try:
            job_id = self.nvim.call('jobstart', cmd, {
                'on_stdout': on_stdout or 'v:lua._xli_job_handler',
                'on_stderr': 'v:lua._xli_job_handler',
                'on_exit': on_exit or 'v:lua._xli_job_exit',
            })
            return job_id
        except Exception as e:
            print(f"Job error: {e}", file=sys.stderr)
            return None

    def system(self, cmd: str) -> str:
        """Выполняет команду через vim.fn.system"""
        if not self.is_connected():
            return ""

        try:
            return self.nvim.call('system', cmd)
        except Exception as e:
            return f"Error: {e}"

    # ─── Context Queries ───

    def get_cwd(self) -> str:
        """Текущая директория Neovim"""
        if not self.is_connected():
            return os.getcwd()

        try:
            return self.nvim.call('getcwd')
        except:
            return os.getcwd()

    def get_current_file(self) -> str:
        """Путь текущего файла"""
        if not self.is_connected():
            return ""

        try:
            return self.nvim.current.buffer.name
        except:
            return ""

    def get_selection(self) -> str:
        """Получает выделенный текст (visual mode)"""
        if not self.is_connected():
            return ""

        try:
            # Сохраняем регистр
            old_reg = self.nvim.call('getreg', '"')
            old_regtype = self.nvim.call('getregtype', '"')

            # Копируем выделение
            self.nvim.command('normal! gv"xy')
            selection = self.nvim.call('getreg', 'x')

            # Восстанавливаем
            self.nvim.call('setreg', '"', old_reg, old_regtype)

            return selection
        except:
            return ""

    def get_buffer_content(self, bufnr: Optional[int] = None) -> List[str]:
        """Содержимое буфера"""
        if not self.is_connected():
            return []

        try:
            if bufnr:
                buf = self.nvim.buffers[bufnr]
            else:
                buf = self.nvim.current.buffer
            return buf[:]  # type: ignore
        except:
            return []

    # ─── Questionnaire (Буфер с вопросами) ───

    def open_questionnaire(self, questions: List[Dict[str, Any]], 
                         on_complete: Callable[[Dict[str, str]], None]) -> Optional[int]:
        """Открывает интерактивный буфер с вопросами"""
        if not self.is_connected():
            return None

        try:
            # Создаём буфер
            buf = self.nvim.api.create_buf(False, True)
            buf.name = "xli://questionnaire"
            buf.options['filetype'] = 'xli_questionnaire'
            buf.options['buftype'] = 'prompt'

            # Формируем содержимое
            lines = [
                " 🔥 XLI PRO — Уточнение задачи ",
                "─" * 60,
                "",
                "Пожалуйста, ответьте на вопросы для уточнения:",
                "",
            ]

            answers = {}
            current_q = 0

            def ask_question(idx: int):
                if idx >= len(questions):
                    # Все вопросы заданы
                    on_complete(answers)
                    self.nvim.command('bdelete! ' + str(buf.number))
                    return

                q = questions[idx]
                q_lines = [
                    f"❓ Вопрос {idx + 1}/{len(questions)}:",
                    f"   {q['question']}",
                    "",
                ]

                if q.get('options'):
                    for i, opt in enumerate(q['options'], 1):
                        q_lines.append(f"   {i}. {opt}")
                    q_lines.append("")
                    q_lines.append("Введите номер ответа и нажмите Enter:")
                else:
                    q_lines.append("Введите ответ и нажмите Enter:")

                buf[:] = lines + q_lines

                # Устанавливаем callback на Enter
                def on_answer():
                    answer = buf[-1] if buf else ""
                    answers[q['id']] = answer.strip()
                    ask_question(idx + 1)

                # Регистрируем callback
                self.nvim.command(f"autocmd TextChanged <buffer={buf.number}> ++once lua _xli_q_callback({idx})")

            ask_question(0)

            # Открываем окно
            self.nvim.command('split')
            win = self.nvim.current.window
            win.buffer = buf
            win.height = min(20, len(lines) + 10)

            return buf.number

        except Exception as e:
            print(f"Questionnaire error: {e}", file=sys.stderr)
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


def get_nvim_bridge() -> NvimBridge:
    """Получить bridge"""
    return NvimBridge()
