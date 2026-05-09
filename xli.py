#!/usr/bin/env python3
"""
XLI PRO ULTIMATE — С интерактивным диалогом опросника
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

console = Console()
fig = Figlet(font='slant')

CSS = """
Screen { background: $surface; }
.results-grid { height: 18; margin: 1; }
.result-panel { border: solid $primary; padding: 1; margin: 1; background: $panel; overflow-y: auto; }
.result-panel.coder { border: solid cyan; }
.result-panel.debugger { border: solid yellow; }
.result-panel.optimizer { border: solid green; }
.progress-bar { margin-top: 1; }
.state-indicator { margin-top: 1; padding: 0 1; }
.activity-log { border: solid $accent; height: 18; margin-top: 1; overflow-y: auto; background: $panel; }
#input-panel { border: solid $primary; margin-top: 1; padding: 1; background: $panel; }
#run-btn { width: 22; }
#task-input { width: 1fr; }
#status-bar { background: $panel; padding: 1; margin-top: 1; }
.result-content { margin-top: 1; }

#dialog-container {
    width: 70;
    height: 40;
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
"""

class XliTui(App):
    CSS = CSS
    BINDINGS = [
        ("ctrl+c", "quit", "Выйти"),
        ("c", "clear_log", "Очистить лог"),
        ("f", "focus_input", "Фокус на ввод"),
        ("m", "show_mcp", "MCP серверы"),
        ("q", "skip_questions", "Пропустить вопросы"),
    ]

    def __init__(self):
        super().__init__()
        self.progress_bars = {}
        self.state_widgets = {}
        self.response_widgets = {}
        self.log_widget = None
        self.skip_questions = False

        self.agents = {
            "coder": XliAgent(
                "CODER",
                AGENT_IDS["coder"],
                "Ты - Кодер. Пишешь код, создаёшь файлы. Команды только в <run>. Используй ПОЛНЫЕ ПУТИ."
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
            with Horizontal():
                yield Static("🔥 XLI PRO ULTIMATE")
                yield Static(f"📅 {datetime.now().strftime('%Y-%m-%d')}")
                yield Static("⚡ CODER → DEBUGGER → OPTIMIZER")
                mcp_count = len(get_available_servers())
                yield Static(f"🔌 MCP: {mcp_count}")

            with Grid(classes="results-grid"):
                for agent_id, title, color in [("coder", "💻 КОДЕР", "cyan"), 
                                                ("debugger", "🐛 ОТЛАДЧИК", "yellow"),
                                                ("optimizer", "🚀 ОПТИМИЗАТОР", "green")]:
                    with Vertical(classes=f"result-panel {agent_id}"):
                        yield Static(f"[bold {color}]{title}[/bold {color}]")
                        self.progress_bars[agent_id] = ProgressBar(total=100, show_percentage=False)
                        yield self.progress_bars[agent_id]
                        self.state_widgets[agent_id] = Static("⚪ ОЖИДАНИЕ")
                        yield self.state_widgets[agent_id]
                        self.response_widgets[agent_id] = Static("Ожидание...", classes="result-content")
                        yield self.response_widgets[agent_id]

            with Collapsible(title="📋 LIVE LOG", collapsed=False):
                self.log_widget = ScrollableContainer(classes="activity-log")
                yield self.log_widget

            with Horizontal(id="input-panel"):
                self.task_input = Input(placeholder="💬 Введите задачу...", id="task-input")
                self.run_button = Button("▶ ЗАПУСТИТЬ", variant="primary", id="run-btn")
                yield self.task_input
                yield self.run_button

            self.status_bar = Static("💡 Enter — запуск | q — пропустить вопросы | m — MCP", id="status-bar")
        yield Footer()

    def on_mount(self):
        self.set_focus(self.task_input)
        self._log("XLI PRO ULTIMATE запущен", "SYS")
        self._log(f"MCP серверов: {len(get_available_servers())}", "SYS")

    def _log(self, msg: str, agent: str = "SYS"):
        if not self.log_widget:
            return
        timestamp = datetime.now().strftime("%H:%M:%S")
        entry = Static(f"{timestamp} [{agent}] {msg}")
        self.log_widget.mount(entry)
        self.log_widget.scroll_end(animate=False)

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
        self._log(f"Опросник {'выключен' if self.skip_questions else 'включён'}", "SYS")

    async def run_chain(self, original_task: str):
        self.clear_results()
        
        final_task = original_task
        dialog_shown = False
        
        if not self.skip_questions and len(original_task.split()) < 20:
            self._log("📋 Открываю диалог уточнения задачи...", "SYS")
            final_task, dialog_shown = await clarify_task_with_dialog(original_task, AGENT_IDS["coder"], self)
            if dialog_shown:
                self._log("✅ Диалог завершён", "SYS")
            if final_task != original_task:
                self._log(f"📝 Уточнённая задача:\n{final_task[:300]}", "SYS")
        
        self._log(f"📌 ЗАДАЧА: {final_task[:200]}", "SYS")
        
        # Цикл агентов
        max_iterations = 3
        iteration = 0
        context = final_task
        completed = False
        
        while iteration < max_iterations and not completed:
            iteration += 1
            self._log(f"🔄 ИТЕРАЦИЯ {iteration}", "SYS")
            
            # Кодер
            self.update_state("coder", "🟡 ПИШЕТ", 30)
            self._log("▶ КОДЕР", "CODER")
            coder_response = await self.agents["coder"].think(context)
            self._log(f"Кодер:\n{coder_response[:300]}", "CODER")
            self.update_response("coder", coder_response[:300])
            self.update_state("coder", "🟢 ГОТОВ", 100)
            
            # Отладчик
            self.update_state("debugger", "🟡 ПРОВЕРЯЕТ", 30)
            self._log("▶ ОТЛАДЧИК", "DEBUGGER")
            debugger_response = await self.agents["debugger"].think(
                f"Проверь код:\n{coder_response}\nЕсли ошибок нет: 'ГОТОВО'"
            )
            self._log(f"Отладчик:\n{debugger_response[:300]}", "DEBUGGER")
            self.update_response("debugger", debugger_response[:300])
            self.update_state("debugger", "🟢 ГОТОВ", 100)
            
            if "НУЖНО ИСПРАВЛЕНИЕ" in debugger_response:
                self._log("⚠️ Возврат к Кодеру", "SYS")
                context = debugger_response
                continue
            
            # Оптимизатор
            self.update_state("optimizer", "🟡 ОПТИМИЗИРУЕТ", 30)
            self._log("▶ ОПТИМИЗАТОР", "OPTIMIZER")
            optimizer_response = await self.agents["optimizer"].think(
                f"Оптимизируй код:\n{coder_response}"
            )
            self._log(f"Оптимизатор:\n{optimizer_response[:300]}", "OPTIMIZER")
            self.update_response("optimizer", optimizer_response[:300])
            self.update_state("optimizer", "🟢 ГОТОВ", 100)
            
            if "НУЖНА ОПТИМИЗАЦИЯ" in optimizer_response:
                self._log("⚡ Возврат к Кодеру", "SYS")
                context = optimizer_response
                continue
            
            completed = True
        
        self._log("✅ ЗАДАЧА ВЫПОЛНЕНА", "SYS")
        self.status_bar.update("✅ Готово!")

    async def on_button_pressed(self, event: Button.Pressed):
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
