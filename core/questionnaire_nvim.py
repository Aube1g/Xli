#!/usr/bin/env python3
"""
XLI Questionnaire for Neovim
Интерактивный буфер с вопросами через Neovim API
"""

import asyncio
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass


@dataclass
class Question:
    id: str
    question: str
    type: str = "text"  # text, choice, confirm
    options: Optional[List[str]] = None
    default: Optional[str] = None
    required: bool = True


class NvimQuestionnaire:
    """Questionnaire через Neovim буфер"""

    def __init__(self, nvim_bridge=None):
        self.nvim = nvim_bridge
        self.answers: Dict[str, str] = {}
        self.questions: List[Question] = []
        self.current_idx = 0
        self._completed = asyncio.Event()
        self._result: Optional[Dict[str, str]] = None

    async def run(self, questions: List[Question]) -> Dict[str, str]:
        """Запускает опросник и ждёт ответов"""
        self.questions = questions
        self.answers = {}
        self.current_idx = 0
        self._completed.clear()

        if self.nvim and self.nvim.is_connected():
            return await self._run_nvim()
        else:
            return await self._run_terminal()

    async def _run_nvim(self) -> Dict[str, str]:
        """Запуск через Neovim буфер"""
        try:
            buf = self.nvim.nvim.api.create_buf(False, True)
            buf.name = "xli://questionnaire"
            buf.options['filetype'] = 'xli_questionnaire'
            buf.options['buftype'] = 'prompt'
            buf.options['bufhidden'] = 'wipe'

            # Создаём окно
            self.nvim.nvim.command('split')
            win = self.nvim.nvim.current.window
            win.buffer = buf
            win.height = 25

            # Устанавливаем клавиши
            self._setup_keymaps(buf.number)

            # Показываем первый вопрос
            self._render_question(buf)

            # Ждём завершения
            await asyncio.wait_for(self._completed.wait(), timeout=300)

            # Закрываем окно
            self.nvim.nvim.command('bdelete! ' + str(buf.number))

            return self._result or self.answers

        except asyncio.TimeoutError:
            print("Questionnaire timeout")
            return self.answers
        except Exception as e:
            print(f"Questionnaire error: {e}")
            return self.answers

    def _setup_keymaps(self, bufnr: int):
        """Настройка клавиш для буфера"""
        if not self.nvim or not self.nvim.is_connected():
            return

        nvim = self.nvim.nvim

        # Enter — подтвердить ответ
        nvim.api.buf_set_keymap(bufnr, 'n', '<CR>', 
            f':lua _xli_q_submit({bufnr})<CR>', 
            {'noremap': True, 'silent': True})

        # 1-9 — выбор варианта
        for i in range(1, 10):
            nvim.api.buf_set_keymap(bufnr, 'n', str(i),
                f':lua _xli_q_select({bufnr}, {i})<CR>',
                {'noremap': True, 'silent': True})

        # q — пропустить / отмена
        nvim.api.buf_set_keymap(bufnr, 'n', 'q',
            f':lua _xli_q_cancel({bufnr})<CR>',
            {'noremap': True, 'silent': True})

        # j/k — навигация
        nvim.api.buf_set_keymap(bufnr, 'n', 'j',
            f':lua _xli_q_next({bufnr})<CR>',
            {'noremap': True, 'silent': True})
        nvim.api.buf_set_keymap(bufnr, 'n', 'k',
            f':lua _xli_q_prev({bufnr})<CR>',
            {'noremap': True, 'silent': True})

    def _render_question(self, buf):
        """Отрисовывает текущий вопрос"""
        if self.current_idx >= len(self.questions):
            self._finish()
            return

        q = self.questions[self.current_idx]
        lines = [
            " 🔥 XLI PRO — Уточнение задачи ",
            "─" * 60,
            "",
            f"❓ Вопрос {self.current_idx + 1}/{len(self.questions)}:",
            f"   {q.question}",
            "",
        ]

        if q.options:
            lines.append("   Варианты ответа:")
            for i, opt in enumerate(q.options, 1):
                selected = "✅" if self.answers.get(q.id) == opt else "  "
                lines.append(f"   {selected} {i}. {opt}")
            lines.append("")
            lines.append("   Нажмите номер варианта или введите текст и Enter")
        else:
            lines.append("   Введите ответ и нажмите Enter")
            if q.default:
                lines.append(f"   (по умолчанию: {q.default})")

        lines.extend([
            "",
            "─" * 60,
            " q — отмена  |  j — следующий  |  k — предыдущий",
        ])

        buf[:] = lines

        # Позиционируем курсор на строку ввода
        if not q.options:
            # Добавляем пустую строку для ввода
            buf.append("")
            buf.append("Ответ: ")

    def _submit_answer(self, answer: str):
        """Обрабатывает ответ"""
        if self.current_idx >= len(self.questions):
            return

        q = self.questions[self.current_idx]

        if not answer and q.default:
            answer = q.default

        if not answer and q.required:
            # Пропускаем обязательный вопрос
            self.nvim.notify(f"⚠️ Требуется ответ на вопрос {self.current_idx + 1}", "warn")
            return

        self.answers[q.id] = answer
        self.current_idx += 1

        if self.current_idx >= len(self.questions):
            self._finish()
        else:
            self._render_question(self.nvim.nvim.current.buffer)

    def _select_option(self, option_idx: int):
        """Выбирает вариант ответа"""
        if self.current_idx >= len(self.questions):
            return

        q = self.questions[self.current_idx]
        if not q.options or option_idx < 1 or option_idx > len(q.options):
            return

        self._submit_answer(q.options[option_idx - 1])

    def _next_question(self):
        """Следующий вопрос (с пропуском текущего)"""
        if self.current_idx < len(self.questions):
            q = self.questions[self.current_idx]
            if not q.required:
                self.current_idx += 1
                self._render_question(self.nvim.nvim.current.buffer)
            else:
                self.nvim.notify("⚠️ Этот вопрос обязательный", "warn")

    def _prev_question(self):
        """Предыдущий вопрос"""
        if self.current_idx > 0:
            self.current_idx -= 1
            self._render_question(self.nvim.nvim.current.buffer)

    def _cancel(self):
        """Отмена опросника"""
        self._result = self.answers
        self._completed.set()

    def _finish(self):
        """Завершение опросника"""
        self._result = self.answers
        self._completed.set()

    async def _run_terminal(self) -> Dict[str, str]:
        """Fallback: терминальный ввод"""
        print("\n" + "=" * 60)
        print(" 🔥 XLI PRO — Уточнение задачи ")
        print("=" * 60)

        for q in self.questions:
            print(f"\n❓ {q.question}")

            if q.options:
                for i, opt in enumerate(q.options, 1):
                    print(f"   {i}. {opt}")

                while True:
                    try:
                        choice = input("   Выберите номер: ").strip()
                        if not choice and q.default:
                            self.answers[q.id] = q.default
                            break
                        idx = int(choice) - 1
                        if 0 <= idx < len(q.options):
                            self.answers[q.id] = q.options[idx]
                            break
                        print("   ❌ Неверный выбор")
                    except ValueError:
                        if not q.required:
                            break
                        print("   ❌ Введите номер")
            else:
                default_hint = f" [{q.default}]" if q.default else ""
                answer = input(f"   Ответ{default_hint}: ").strip()
                if not answer and q.default:
                    answer = q.default
                self.answers[q.id] = answer

        print("\n✅ Уточнение завершено!")
        print("=" * 60)

        return self.answers


# Глобальные callbacks для Neovim Lua
_questionnaires: Dict[int, NvimQuestionnaire] = {}


def _xli_q_submit(bufnr: int):
    """Callback: подтвердить ответ"""
    q = _questionnaires.get(bufnr)
    if q:
        # Получаем последнюю строку как ответ
        buf = q.nvim.nvim.buffers[bufnr]
        answer = buf[-1].replace("Ответ: ", "").strip() if buf else ""
        q._submit_answer(answer)


def _xli_q_select(bufnr: int, idx: int):
    """Callback: выбрать вариант"""
    q = _questionnaires.get(bufnr)
    if q:
        q._select_option(idx)


def _xli_q_next(bufnr: int):
    """Callback: следующий вопрос"""
    q = _questionnaires.get(bufnr)
    if q:
        q._next_question()


def _xli_q_prev(bufnr: int):
    """Callback: предыдущий вопрос"""
    q = _questionnaires.get(bufnr)
    if q:
        q._prev_question()


def _xli_q_cancel(bufnr: int):
    """Callback: отмена"""
    q = _questionnaires.get(bufnr)
    if q:
        q._cancel()


async def clarify_task_nvim(task: str, agent_id: str, nvim_bridge=None) -> tuple:
    """Уточнение задачи через Neovim буфер"""

    # Генерируем вопросы через AI
    from core.mistral_client import call_mistral_agent

    prompt = f"""Задача: {task}

Сгенерируй 2-4 уточняющих вопроса для лучшего понимания задачи.
Формат: JSON массив объектов с полями: id, question, type (text/choice), options (список вариантов, если choice).

Пример:
[
  {{"id": "framework", "question": "Какой фреймворк использовать?", "type": "choice", "options": ["React", "Vue", "Svelte"]}},
  {{"id": "styling", "question": "Какой подход к стилям?", "type": "choice", "options": ["CSS modules", "Styled-components", "Tailwind"]}},
  {{"id": "details", "question": "Дополнительные требования?", "type": "text", "default": "Нет"}}
]"""

    try:
        response = await call_mistral_agent(agent_id, [
            {"role": "system", "content": "Ты помогаешь уточнить задачи. Отвечай только JSON массивом."},
            {"role": "user", "content": prompt}
        ])

        # Парсим JSON
        import json
        # Извлекаем JSON из ответа
        json_match = __import__('re').search(r'\[.*\]', response, __import__('re').DOTALL)
        if json_match:
            questions_data = json.loads(json_match.group())
        else:
            questions_data = json.loads(response)

        questions = [Question(**q) for q in questions_data]

    except Exception as e:
        # Fallback: простые вопросы
        questions = [
            Question("language", "На каком языке писать?", "choice", 
                    ["Python", "JavaScript", "TypeScript", "Go", "Rust"]),
            Question("framework", "Использовать фреймворк?", "choice",
                    ["Нет (vanilla)", "React", "Vue", "FastAPI", "Flask"]),
            Question("details", "Дополнительные требования?", "text", default="Нет"),
        ]

    # Запускаем опросник
    q = NvimQuestionnaire(nvim_bridge)

    if nvim_bridge and nvim_bridge.is_connected():
        # Регистрируем для callbacks
        buf = nvim_bridge.nvim.api.create_buf(False, True)
        _questionnaires[buf.number] = q

    answers = await q.run(questions)

    # Формируем уточнённую задачу
    clarified = task
    for q_obj in questions:
        if q_obj.id in answers and answers[q_obj.id]:
            clarified += f"\n\n[{q_obj.id.upper()}]: {answers[q_obj.id]}"

    return clarified, True
