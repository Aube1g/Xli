#!/usr/bin/env python3
"""
Менеджер плагинов XLI — загрузка, регистрация, lifecycle
"""

import importlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional
from dataclasses import dataclass, field

BASE_DIR = Path.home() / ".xli"
PLUGINS_DIR = BASE_DIR / "plugins"
PLUGINS_CONFIG = BASE_DIR / "plugins_config.json"


@dataclass
class PluginInfo:
    """Метаданные плагина"""
    name: str
    version: str
    description: str = ""
    author: str = ""
    entry_point: str = "main"
    ui_components: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    enabled: bool = True
    path: Path = None


class PluginManager:
    """Центральный менеджер плагинов"""

    def __init__(self, app=None):
        self.app = app
        self.plugins: Dict[str, PluginInfo] = {}
        self.instances: Dict[str, Any] = {}
        self.hooks: Dict[str, List[Callable]] = {
            "pre_coder": [],
            "post_coder": [],
            "pre_debugger": [],
            "post_debugger": [],
            "pre_optimizer": [],
            "post_optimizer": [],
            "on_task_complete": [],
            "on_ui_mount": [],
            "on_log": [],
        }
        self.ui_contributions: Dict[str, List[Dict]] = {
            "sidebar": [],
            "toolbar": [],
            "panel": [],
            "dialog": [],
            "statusbar": [],
        }
        self._load_all_plugins()

    def _load_all_plugins(self):
        """Сканирует и загружает все плагины"""
        if not PLUGINS_DIR.exists():
            PLUGINS_DIR.mkdir(parents=True)
            return

        config = self._load_config()

        for plugin_dir in PLUGINS_DIR.iterdir():
            if not plugin_dir.is_dir():
                continue

            manifest = plugin_dir / "manifest.json"
            if not manifest.exists():
                continue

            try:
                with open(manifest, "r", encoding="utf-8") as f:
                    data = json.load(f)

                info = PluginInfo(
                    name=data["name"],
                    version=data.get("version", "0.1.0"),
                    description=data.get("description", ""),
                    author=data.get("author", ""),
                    entry_point=data.get("entry_point", "main"),
                    ui_components=data.get("ui", []),
                    hooks=data.get("hooks", []),
                    enabled=config.get(data["name"], {}).get("enabled", True),
                    path=plugin_dir,
                )

                self.plugins[info.name] = info

                if info.enabled:
                    self._activate_plugin(info)

            except Exception as e:
                print(f"❌ Ошибка загрузки плагина {plugin_dir.name}: {e}")

    def _load_config(self) -> dict:
        if PLUGINS_CONFIG.exists():
            with open(PLUGINS_CONFIG, "r") as f:
                return json.load(f)
        return {}

    def _save_config(self):
        config = {name: {"enabled": info.enabled} for name, info in self.plugins.items()}
        with open(PLUGINS_CONFIG, "w") as f:
            json.dump(config, f, indent=2)

    def _activate_plugin(self, info: PluginInfo):
        """Активирует плагин: импортирует и регистрирует"""
        try:
            plugin_path = str(info.path)
            if plugin_path not in sys.path:
                sys.path.insert(0, plugin_path)

            main_file = info.path / "main.py"
            if not main_file.exists():
                print(f"⚠️ Плагин {info.name}: main.py не найден")
                return

            spec = importlib.util.spec_from_file_location(
                f"plugin_{info.name}", str(main_file)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            entry = getattr(module, info.entry_point, None)

            if entry is None:
                print(f"⚠️ Плагин {info.name}: entry_point '{info.entry_point}' не найден")
                return

            # Создаём экземпляр
            if inspect.isclass(entry):
                instance = entry(self.app, self)
                self.instances[info.name] = instance
            elif callable(entry):
                instance = entry(self.app, self)
                self.instances[info.name] = instance
            else:
                print(f"⚠️ Плагин {info.name}: entry_point не вызываемый")
                return

            # Регистрируем хуки
            self._register_hooks(info, instance)

            # Регистрируем UI-компоненты
            self._register_ui(info, instance)

            print(f"✅ Плагин {info.name} v{info.version} активирован")

        except Exception as e:
            print(f"❌ Ошибка активации плагина {info.name}: {e}")
            import traceback
            traceback.print_exc()

    def _register_hooks(self, info: PluginInfo, instance):
        """Регистрирует хуки плагина"""
        for hook_name in info.hooks:
            if hook_name not in self.hooks:
                continue

            handler = None
            if hasattr(instance, hook_name):
                handler = getattr(instance, hook_name)

            if handler and callable(handler):
                self.hooks[hook_name].append(handler)
                print(f"  🔗 Хук {hook_name} зарегистрирован")

    def _register_ui(self, info: PluginInfo, instance):
        """Регистрирует UI-компоненты плагина"""
        for component_type in info.ui_components:
            if component_type not in self.ui_contributions:
                continue

            ui_method = f"get_{component_type}_widget"
            if hasattr(instance, ui_method):
                try:
                    widget = getattr(instance, ui_method)()
                    if widget:
                        self.ui_contributions[component_type].append({
                            "plugin": info.name,
                            "widget": widget,
                            "instance": instance,
                        })
                        print(f"  🎨 UI {component_type} зарегистрирован")
                except Exception as e:
                    print(f"  ⚠️ Ошибка UI {component_type}: {e}")

    def execute_hook(self, hook_name: str, *args, **kwargs) -> Any:
        """Выполняет все обработчики хука"""
        results = []
        for handler in self.hooks.get(hook_name, []):
            try:
                if inspect.iscoroutinefunction(handler):
                    pass
                else:
                    result = handler(*args, **kwargs)
                    results.append(result)
            except Exception as e:
                print(f"❌ Ошибка в хуке {hook_name}: {e}")
        return results

    async def execute_hook_async(self, hook_name: str, *args, **kwargs) -> Any:
        """Выполняет async хуки"""
        results = []
        for handler in self.hooks.get(hook_name, []):
            try:
                if inspect.iscoroutinefunction(handler):
                    result = await handler(*args, **kwargs)
                    results.append(result)
                else:
                    result = handler(*args, **kwargs)
                    results.append(result)
            except Exception as e:
                print(f"❌ Ошибка в async хуке {hook_name}: {e}")
        return results

    def get_ui_widgets(self, component_type: str) -> List:
        """Возвращает все UI-виджеты указанного типа"""
        return self.ui_contributions.get(component_type, [])

    def toggle_plugin(self, name: str, enabled: bool):
        """Включает/выключает плагин"""
        if name in self.plugins:
            self.plugins[name].enabled = enabled
            self._save_config()

    def list_plugins(self) -> List[PluginInfo]:
        """Возвращает список всех плагинов"""
        return list(self.plugins.values())


def get_plugin_manager(app=None) -> PluginManager:
    """Singleton для PluginManager"""
    if not hasattr(get_plugin_manager, "_instance"):
        get_plugin_manager._instance = PluginManager(app)
    return get_plugin_manager._instance
