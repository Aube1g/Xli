#!/usr/bin/env python3
"""
XLI PRO ULTIMATE — Система плагинов + Умный пайплайн
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / ".xli"))

from textual.app import App
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer, Grid
from textual.widgets import Header, Footer, Button, Static, Input, Collapsible, ProgressBar
from rich.text import Text
from rich.console import Console
from rich.panel import Panel
from pyfiglet import Figlet

from core.mistral_client import AGENT_IDS
from core.mcp_client import get_available_servers, list_mcp_servers
from core.agents import XliAgent
from core.questionnaire import clarify_task_with_dialog
from core.plugin_manager import PluginManager, get_plugin_manager

console = Console()
fig = Figlet(font='slant')

CSS = """
Screen { background: $surface; }

/* Основная сетка агентов */
.results-grid { 
    grid-size: 3;
    grid-columns: 1fr 1fr 1fr;
    grid-rows: auto;
    height: auto; 
    margin: 1; 
}
.result-panel { 
    border: solid $primary; 
    padding: 1; 
    margin: 1; 
    background: $panel; 
    overflow-y: auto; 
    height: auto;
}
.result-panel.coder { border: solid cyan; }
.result-panel.debugger { border: solid yellow; }
.result-panel.optimizer { border: solid green; }

/* Прогресс и статусы */
.progress-bar { margin-top: 1; }
.state-indicator { margin-top: 1; padding: 0 1; }
.result-content { margin-top: 1; }

/* Лог */
.activity-log { 
    border: solid $accent; 
    height: 18; 
    margin-top: 1; 
    overflow-y: auto; 
    background: $panel; 
}

/* Ввод */
#input-panel { 
    border: solid $primary; 
    margin-top: 1; 
    padding: 1; 
    background: $panel; 
}
#run-btn { width: 22; }
#task-input { width: 1fr; }

/* Статус бар */
#status-bar { 
    background: $panel; 
    padding: 1; 
    margin-top: 1; 
}

/* Диалог */
#dialog-container {
    width: 70;
    height: auto;
    border: solid $primary;
    background: $surface;
    padding: 2;
}
#dialog-title {
    margin-bottom: 1;
    text-style: bold;
}
#dialog-question {
    margin-bottom: 2;
}
#dialog-buttons {
    margin-top: 2;
    align: center middle;
}

/* ====== ПЛАГИНЫ ====== */
#plugins-section {
    border: solid magenta 60%;
    height: auto;
    margin: 1;
    padding: 1;
    background: $surface-darken-1;
}
.plugins-title {
    text-style: bold;
    text-align: center;
    color: magenta;
    margin-bottom: 1;
}
.plugin-toolbar {
    height: auto;
    align: center middle;
    margin-top: 1;
    margin-bottom: 1;
}
.plugin-panel {
    border: solid cyan 60%;
    padding: 1;
    margin: 1;
    background: $panel;
    height: auto;
}
.plugin-panel-title {
    text-style: bold;
    color: cyan;
    margin-bottom: 1;
}
"""


class XliTui(App):
    CSS = CSS
    BINDINGS = [
        ("ctrl+c", "quit", "Выйти"),
        ("c", "clear_log", "Очистить лог"),
        ("f", "focus_input", "Фокус на ввод"),
        ("m", "show_mcp", "MCP серверы"),
        ("q", "skip_questions", "Пропустить вопросы"),
        ("p", "show_plugins", "Плагины"),
    ]

    def __init__(self):
        super().__init__()
        self.progress_bars = {}
        self.state_widgets = {}
        self.response_widgets = {}
        self.log_widget = None
        self.skip_questions = False
        self.plugin_manager = None
        self.plugin_panels = {}

        # ====== ИНИЦИАЛИЗАЦИЯ ПЛАГИНОВ ЗДЕСЬ! ======
        # compose() вызывается ДО on_mount(), поэтому плагины
        # должны быть загружены в __init__()
        try:
            self.plugin_manager = get_plugin_manager(self)
        except Exception as e:
            print(f"⚠️ Ошибка инициализации плагинов: {e}")
            self.plugin_manager = None

        self.agents = {
            "coder": XliAgent(
                "CODER",
                AGENT_IDS["coder"],
                "Ты - Кодер. Пишешь код, создаешь файлы. Команды только в <run>. Используй ПОЛНЫЕ ПУТИ."
            ),
            "debugger": XliAgent(
                "DEBUGGER",
                AGENT_IDS["debugger"],
                "Ты - Отладчик. Если ошибки есть, напиши 'НУЖНО ИСПРАВЛЕНИЕ'."
            ),
            "optimizer": XliAgent(
                "OPTIMIZER",
                AGENT_IDS["optimizer"],
                "Ты - Оптимизатор. Если нужны улучшения, напиши 'НУЖНА ОПТИМИЗАЦИЯ'."
            ),
        }

    def compose(self):
        yield Header(show_clock=True)

        with Container():
            # === ШАПКА ===
            with Horizontal():
                yield Static("🔥 XLI PRO ULTIMATE")
                yield Static(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
                yield Static("⚡ CODER → DEBUGGER → OPTIMIZER")
                mcp_count = len(get_available_servers())
                yield Static(f"🔌 MCP: {mcp_count}")

            # === ПЛАГИНЫ: Toolbar (кнопки над агентами) ===
            if self.plugin_manager:
                toolbar_widgets = self.plugin_manager.get_ui_widgets("toolbar")
                if toolbar_widgets:
                    with Horizontal(classes="plugin-toolbar"):
                        for contrib in toolbar_widgets:
                            yield contrib["widget"]

            # === ОСНОВНАЯ СЕТКА: 3 агента ===
            with Grid(classes="results-grid"):
                for agent_id, title, color in [
                    ("coder", "💻 КОДЕР", "cyan"), 
                    ("debugger", "🐛 ОТЛАДЧИК", "yellow"),
                    ("optimizer", "🚀 ОПТИМИЗАТОР", "green")
                ]:
                    with Vertical(classes=f"result-panel {agent_id}"):
                        yield Static(f"[bold {color}]{title}[/bold {color}]")
                        self.progress_bars[agent_id] = ProgressBar(total=100, show_percentage=False)
                        yield self.progress_bars[agent_id]
                        self.state_widgets[agent_id] = Static("⚪ ОЖИДАНИЕ")
                        yield self.state_widgets[agent_id]
                        self.response_widgets[agent_id] = Static("Ожидание...", classes="result-content")
                        yield self.response_widgets[agent_id]

            # === ПЛАГИНЫ: Отдельная секция (ВНЕ Grid!) ===
            if self.plugin_manager:
                panel_widgets = self.plugin_manager.get_ui_widgets("panel")
                if panel_widgets:
                    with Container(id="plugins-section"):
                        yield Static("🔌 ПЛАГИНЫ", classes="plugins-title")

                        for contrib in panel_widgets:
                            name = contrib["plugin"]
                            widget = contrib["widget"]

                            with Vertical(classes="plugin-panel"):
                                yield Static(f"📦 {name}", classes="plugin-panel-title")
                                yield widget
                                self.plugin_panels[name] = widget

            # === ЛОГ ===
            with Collapsible(title="📋 LIVE LOG", collapsed=False):
                self.log_widget = ScrollableContainer(classes="activity-log")
                yield self.log_widget

            # === ВВОД ===
            with Horizontal(id="input-panel"):
                self.task_input = Input(placeholder="💬 Введите задачу...", id="task-input")
                self.run_button = Button("▶ ЗАПУСТИТЬ", variant="primary", id="run-btn")
                yield self.task_input
                yield self.run_button

            # === СТАТУС ===
            self.status_bar = Static(
                "💡 Enter — запуск | q — пропустить вопросы | m — MCP | p — плагины", 
                id="status-bar"
            )

        yield Footer()

    def on_mount(self):
        # Логируем загрузку плагинов
        if self.plugin_manager:
            count = len(self.plugin_manager.list_plugins())
            self._log(f"🔌 Плагинов загружено: {count}", "SYS")

        self.set_focus(self.task_input)
        self._log("XLI PRO ULTIMATE запущен", "SYS")
        self._log(f"MCP серверов: {len(get_available_servers())}", "SYS")

        # Хук on_ui_mount
        if self.plugin_manager:
            asyncio.create_task(self.plugin_manager.execute_hook_async("on_ui_mount", self))

    def _log(self, msg: str, agent: str = "SYS"):
        if not self.log_widget:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = Static(f"{timestamp} [{agent}] {msg}")
        self.log_widget.mount(entry)
        self.log_widget.scroll_end(animate=False)

        if self.plugin_manager:
            self.plugin_manager.execute_hook("on_log", msg, agent)

    def update_state(self, agent_key: str, state: str, progress: int):
        if agent_key in self.state_widgets:
            self.state_widgets[agent_key].update(state)
        if agent_key in self.progress_bars:
            self.progress_bars[agent_key].progress = progress

    def update_response(self, agent_key: str, response: str):
        if agent_key in self.response_widgets:
            self.response_widgets[agent_key].update(response[:300] if response else "Нет ответа")

    def clear_results(self):
        for key in ["coder", "debugger", "optimizer"]:
            self.update_response(key, "Ожидание...")
            self.update_state(key, "⚪ ОЖИДАНИЕ", 0)

    def action_show_mcp(self):
        servers = list_mcp_servers()
        if not servers:
            self._log("Нет MCP серверов", "SYS")
            return
        self._log("=== MCP СЕРВЕРЫ ===", "SYS")
        for name, info in servers.items():
            self._log(f"{'✅' if info['available'] else '❌'} {name}: {info['description'][:40]}", "MCP")

    def action_skip_questions(self):
        self.skip_questions = not self.skip_questions
        self._log(f"Опросник {'выключен' if self.skip_questions else 'включен'}", "SYS")

    def action_show_plugins(self):
        """Показывает список плагинов"""
        if not self.plugin_manager:
            self._log("❌ Менеджер плагинов не загружен", "SYS")
            return
        plugins = self.plugin_manager.list_plugins()
        self._log("=== ПЛАГИНЫ ===", "SYS")
        for p in plugins:
            status = "✅" if p.enabled else "❌"
            self._log(f"{status} {p.name} v{p.version} — {p.description[:50]}", "PLUGIN")

    def _needs_debug(self, coder_response: str) -> bool:
        """Определяет, нужна ли отладка по ответу кодера"""
        error_keywords = [
            "ошибка", "error", "exception", "traceback", "bug", 
            "не работает", "нужно исправление", "нужно исправить",
            "syntax", "import error", "nameerror", "typeerror",
            "valueerror", "attributeerror", "indentationerror",
            "failed", "fail", "не удалось", "не получилось"
        ]
        response_lower = coder_response.lower()
        return any(kw in response_lower for kw in error_keywords)

    def _needs_optimize(self, coder_response: str, debugger_response: str = "") -> bool:
        """Определяет, нужна ли оптимизация"""
        optimize_keywords = [
            "медленно", "slow", "performance", "memory leak",
            "нужна оптимизация", "ускорить", "улучшить",
            "inefficient", "bottleneck", "optimize", "refactor"
        ]
        combined = (coder_response + " " + debugger_response).lower()
        return any(kw in combined for kw in optimize_keywords)

    async def run_chain(self, original_task: str):
        self.clear_results()

        final_task = original_task
        dialog_shown = False

        # === ШАГ 1: Диалог уточнения ===
        if not self.skip_questions and len(original_task.split()) < 20:
            self._log("📋 Открываю диалог уточнения задачи...", "SYS")
            final_task, dialog_shown = await clarify_task_with_dialog(
                original_task, AGENT_IDS["coder"], self
            )
            if dialog_shown:
                self._log("✅ Диалог завершен", "SYS")
            if final_task != original_task:
                self._log(f"📝 Уточненная задача:\n{final_task[:300]}", "SYS")

        self._log(f"📌 ЗАДАЧА: {final_task[:200]}", "SYS")

        # === ШАГ 2: КОДЕР (всегда, с MCP pre/post) ===
        self.update_state("coder", "🟡 ПИШЕТ", 30)
        self._log("▶ КОДЕР [MCP: knowledge_base → code → auto_tester]", "CODER")

        if self.plugin_manager:
            await self.plugin_manager.execute_hook_async("pre_coder", final_task)

        coder_response = await self.agents["coder"].think(final_task, use_mcp=True)

        if self.plugin_manager:
            await self.plugin_manager.execute_hook_async("post_coder", final_task, coder_response)

        self._log(f"Кодер:\n{coder_response[:300]}", "CODER")
        self.update_response("coder", coder_response[:300])
        self.update_state("coder", "🟢 ГОТОВ", 100)

        # === ШАГ 3: Проверяем, нужна ли отладка ===
        needs_debug = self._needs_debug(coder_response)

        if needs_debug:
            self.update_state("debugger", "🟡 ПРОВЕРЯЕТ", 30)
            self._log("▶ ОТЛАДЧИК [MCP: debugger → auto_tester]", "DEBUGGER")

            if self.plugin_manager:
                await self.plugin_manager.execute_hook_async("pre_debugger", coder_response)

            debugger_response = await self.agents["debugger"].think(
                f"Проверь код:\n{coder_response}\nЕсли ошибок нет: 'ГОТОВО'",
                use_mcp=True
            )

            if self.plugin_manager:
                await self.plugin_manager.execute_hook_async("post_debugger", coder_response, debugger_response)

            self._log(f"Отладчик:\n{debugger_response[:300]}", "DEBUGGER")
            self.update_response("debugger", debugger_response[:300])
            self.update_state("debugger", "🟢 ГОТОВ", 100)

            # Если отладчик нашёл ошибки — возвращаем к кодеру (1 retry)
            if "НУЖНО ИСПРАВЛЕНИЕ" in debugger_response:
                self._log("⚠️ Возврат к Кодеру для исправления", "SYS")
                self.update_state("coder", "🟡 ИСПРАВЛЯЕТ", 50)

                fix_task = f"Исправь ошибки:\n{debugger_response[:500]}\n\nКод:\n{coder_response[:500]}"
                coder_response = await self.agents["coder"].think(fix_task, use_mcp=True)

                self._log(f"Кодер (исправлено):\n{coder_response[:300]}", "CODER")
                self.update_response("coder", coder_response[:300])
                self.update_state("coder", "🟢 ИСПРАВЛЕНО", 100)

                # Повторная проверка
                needs_debug = self._needs_debug(coder_response)
                if needs_debug:
                    self.update_state("debugger", "⚠️ ЕЩЕ ОШИБКИ", 100)
                    self.update_response("debugger", "Ошибки остались после исправления")
                    self._log("❌ Ошибки не исправлены полностью", "SYS")
        else:
            self.update_state("debugger", "⚪ ПРОПУЩЕН", 100)
            self.update_response("debugger", "✅ Код без ошибок")
            self._log("✅ Код без ошибок, отладка пропущена", "SYS")
            debugger_response = ""

        # === ШАГ 4: Проверяем, нужна ли оптимизация ===
        needs_optimize = self._needs_optimize(coder_response, debugger_response)

        if needs_optimize:
            self.update_state("optimizer", "🟡 ОПТИМИЗИРУЕТ", 30)
            self._log("▶ ОПТИМИЗАТОР [MCP: refactor/architecture → auto_tester]", "OPTIMIZER")

            if self.plugin_manager:
                await self.plugin_manager.execute_hook_async("pre_optimizer", coder_response)

            optimizer_response = await self.agents["optimizer"].think(
                f"Оптимизируй код:\n{coder_response}",
                use_mcp=True
            )

            if self.plugin_manager:
                await self.plugin_manager.execute_hook_async("post_optimizer", coder_response, optimizer_response)

            self._log(f"Оптимизатор:\n{optimizer_response[:300]}", "OPTIMIZER")
            self.update_response("optimizer", optimizer_response[:300])
            self.update_state("optimizer", "🟢 ГОТОВ", 100)

            # Если оптимизатор предложил улучшения — применяем
            if "НУЖНА ОПТИМИЗАЦИЯ" in optimizer_response:
                self._log("⚡ Применяю оптимизацию", "SYS")
                self.update_state("coder", "🟡 ОПТИМИЗИРУЕТ", 60)

                optimize_task = f"Примени оптимизацию:\n{optimizer_response[:500]}\n\nКод:\n{coder_response[:500]}"
                coder_response = await self.agents["coder"].think(optimize_task, use_mcp=True)

                self._log(f"Кодер (оптимизировано):\n{coder_response[:300]}", "CODER")
                self.update_response("coder", coder_response[:300])
                self.update_state("coder", "🟢 ОПТИМИЗИРОВАНО", 100)
        else:
            self.update_state("optimizer", "⚪ ПРОПУЩЕН", 100)
            self.update_response("optimizer", "✅ Оптимизация не требуется")
            self._log("✅ Оптимизация не требуется", "SYS")

        # === Хук завершения ===
        if self.plugin_manager:
            await self.plugin_manager.execute_hook_async("on_task_complete", final_task, {
                "coder": coder_response,
                "debugger": debugger_response if needs_debug else None,
                "optimizer": optimizer_response if needs_optimize else None,
            })

        self._log("✅ ЗАДАЧА ВЫПОЛНЕНА", "SYS")
        self.status_bar.update("✅ Готово!")

    async def on_button_pressed(self, event: Button.Pressed):
        # 🔌 Сначала пробуем плагины
        plugin_handled = False
        if self.plugin_manager:
            for contrib in self.plugin_manager.get_ui_widgets("panel") + \
                           self.plugin_manager.get_ui_widgets("toolbar"):
                instance = contrib.get("instance")
                if instance and hasattr(instance, "on_button_pressed"):
                    try:
                        await instance.on_button_pressed(event)
                        plugin_handled = True
                    except Exception as e:
                        self._log(f"❌ Ошибка плагина: {e}", "PLUGIN")

        # Если плагин обработал — останавливаемся
        if plugin_handled:
            return

        # Стандартные кнопки
        if event.button.id == "run-btn":
            task = self.task_input.value.strip()
            if task:
                self.task_input.value = ""
                await self.run_chain(task)
                self.set_focus(self.task_input)

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "task-input":
            task = event.value.strip()
            if task:
                self.task_input.value = ""
                asyncio.create_task(self.run_chain(task))
                self.set_focus(self.task_input)

    def action_clear_log(self):
        if self.log_widget:
            self.log_widget.children.clear()
        self._log("Лог очищен", "SYS")

    def action_focus_input(self):
        self.set_focus(self.task_input)


if __name__ == "__main__":
    console = Console()
    title = fig.renderText("XLI")
    console.print(Panel(Text(title, style="bold cyan"), border_style="bright_cyan",
                       subtitle=f"[dim]{datetime.now().strftime('%H:%M:%S')}[/dim]", subtitle_align="center"))
    console.print(f"[dim]MCP серверов: {len(get_available_servers())}[/dim]")
    console.print("")

    XliTui().run()
