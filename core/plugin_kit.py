#!/usr/bin/env python3
"""
PluginKit — расширенные возможности для плагинов Xli
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, Callable, Optional
from textual.screen import ModalScreen
from textual.containers import Container, Horizontal
from textual.widgets import Button, Label, Static


class ConfirmScreen(ModalScreen):
    """Модальное окно с подтверждением"""
    
    def __init__(self, title: str, message: str):
        super().__init__()
        self.dialog_title = title
        self.dialog_message = message
    
    def compose(self):
        with Container(id="dialog-container"):
            yield Static(self.dialog_title, id="dialog-title")
            yield Static(self.dialog_message, id="dialog-question")
            with Horizontal(id="dialog-buttons"):
                yield Button("✅ Да", variant="primary", id="dialog-yes")
                yield Button("❌ Нет", variant="default", id="dialog-no")
    
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "dialog-yes":
            self.dismiss(True)
        else:
            self.dismiss(False)


class InputScreen(ModalScreen):
    """Модальное окно с полем ввода"""
    
    def __init__(self, title: str, prompt: str, default: str = ""):
        super().__init__()
        self.dialog_title = title
        self.prompt = prompt
        self.default = default
    
    def compose(self):
        from textual.widgets import Input
        
        with Container(id="dialog-container"):
            yield Static(self.dialog_title, id="dialog-title")
            yield Static(self.prompt, id="dialog-question")
            self.input = Input(self.default, placeholder="Введите значение...")
            yield self.input
            with Horizontal(id="dialog-buttons"):
                yield Button("✅ ОК", variant="primary", id="dialog-ok")
                yield Button("❌ Отмена", variant="default", id="dialog-cancel")
    
    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "dialog-ok":
            self.dismiss(self.input.value)
        else:
            self.dismiss(None)


class PluginKit:
    """Набор утилит для плагинов Xli"""
    
    def __init__(self, app, plugin_name: str):
        self.app = app
        self.name = plugin_name
        self._storage: Optional[Dict[str, Any]] = None
        self._storage_path = Path.home() / ".xli" / f"plugin_{plugin_name}.json"
    
    @property
    def storage(self) -> Dict[str, Any]:
        """Персистентное хранилище для плагина (автосохранение)"""
        if self._storage is None:
            if self._storage_path.exists():
                try:
                    with open(self._storage_path, "r") as f:
                        self._storage = json.load(f)
                except:
                    self._storage = {}
            else:
                self._storage = {}
        return self._storage
    
    def save_storage(self):
        """Принудительно сохранить хранилище"""
        if self._storage is not None:
            self._storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._storage_path, "w") as f:
                json.dump(self._storage, f, indent=2, ensure_ascii=False)
    
    def run_in_background(self, func: Callable, *args, **kwargs):
        """Запустить синхронную функцию в фоне (не блокирует UI)"""
        return asyncio.create_task(asyncio.to_thread(func, *args, **kwargs))
    
    async def show_confirm(self, title: str, message: str) -> bool:
        """Показать модальное окно с Yes/No"""
        result = await self.app.push_screen_wait(ConfirmScreen(title, message))
        return result is True
    
    async def show_input(self, title: str, prompt: str, default: str = "") -> Optional[str]:
        """Показать модальное окно с полем ввода"""
        return await self.app.push_screen_wait(InputScreen(title, prompt, default))
    
    def add_toolbar_button(self, label: str, handler, after_id: str = None):
        """Динамически добавить кнопку в тулбар"""
        btn_id = f"plugin_{self.name}_btn_{label.replace(' ', '_')}"
        btn = Button(label, variant="default", id=btn_id)
        
        # Сохраняем обработчик
        if not hasattr(self.app, "_plugin_button_handlers"):
            self.app._plugin_button_handlers = {}
        self.app._plugin_button_handlers[btn_id] = handler
        
        # Находим тулбар и добавляем кнопку
        toolbar = self.app.query_one(".plugin-toolbar")
        if after_id:
            # Вставить после указанной кнопки
            target = self.app.query_one(f"#{after_id}")
            if target:
                toolbar.insert(btn, after=after_id)
            else:
                toolbar.mount(btn)
        else:
            toolbar.mount(btn)
        
        self.app._log(f"➕ Кнопка '{label}' добавлена в тулбар", "PLUGIN")
        return btn_id
    
    def remove_toolbar_button(self, btn_id: str):
        """Удалить кнопку из тулбара"""
        try:
            btn = self.app.query_one(f"#{btn_id}")
            btn.remove()
            if hasattr(self.app, "_plugin_button_handlers"):
                self.app._plugin_button_handlers.pop(btn_id, None)
            self.app._log(f"➖ Кнопка {btn_id} удалена", "PLUGIN")
        except Exception as e:
            self.app._log(f"❌ Не удалось удалить кнопку: {e}", "PLUGIN")
    
    def log(self, message: str):
        """Удобный лог с именем плагина"""
        self.app._log(f"[{self.name}] {message}", "PLUGIN")
