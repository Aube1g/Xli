#!/usr/bin/env python3
"""
Расширенный менеджер плагинов с горячей перезагрузкой
ФИКСЫ:
  - plugin_paths инициализирован
  - _plugin_manager_instance объявлен глобально
  - clear_all_hooks() и clear_all_ui() для избежания утечек
  - правильная очистка sys.modules
"""

import importlib
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from core.plugin_manager import PluginManager, get_plugin_manager, PLUGINS_DIR

# ФИКС: Глобальная переменная объявлена здесь
_plugin_manager_instance = None


class ExtendedPluginManager(PluginManager):
    """Менеджер плагинов с поддержкой горячей перезагрузки"""

    def __init__(self, app):
        # ФИКС: Инициализируем plugin_paths ДО вызова super().__init__
        self.plugin_paths = [PLUGINS_DIR]
        self._loaded_modules: Dict[str, Any] = {}

        super().__init__(app)

    def clear_all_hooks(self):
        """ФИКС: Очищает все хуки перед перезагрузкой"""
        for hook_name, handlers in self.hooks.items():
            handlers.clear()

    def clear_all_ui(self):
        """ФИКС: Очищает все UI-контрибуции перед перезагрузкой"""
        for component_type, contributions in self.ui_contributions.items():
            contributions.clear()

    def reload_plugin(self, plugin_name: str) -> bool:
        """Перезагрузить конкретный плагин"""
        if plugin_name not in self.plugins:
            return False

        # Находим модуль
        module_path = None
        for path in self.plugin_paths:
            plugin_dir = path / plugin_name
            if plugin_dir.is_dir() and (plugin_dir / "main.py").exists():
                module_path = plugin_dir / "main.py"
                break
            elif (path / f"{plugin_name}.py").exists():
                module_path = path / f"{plugin_name}.py"
                break

        if not module_path:
            return False

        try:
            # Очищаем старые хуки этого плагина
            info = self.plugins[plugin_name]
            for hook_name in info.hooks:
                if hook_name in self.hooks:
                    # Удаляем хуки, принадлежащие этому плагину
                    old_instance = self.instances.get(plugin_name)
                    self.hooks[hook_name] = [
                        h for h in self.hooks[hook_name]
                        if not (hasattr(h, '__self__') and h.__self__ is old_instance)
                    ]

            # Очищаем UI этого плагина
            for component_type, contributions in self.ui_contributions.items():
                self.ui_contributions[component_type] = [
                    c for c in contributions
                    if c.get("plugin") != plugin_name
                ]

            # Удаляем старый экземпляр
            if plugin_name in self.instances:
                del self.instances[plugin_name]

            # Выгружаем старый модуль
            if plugin_name in self._loaded_modules:
                del self._loaded_modules[plugin_name]

            # ФИКС: Очищаем из sys.modules все связанные модули
            module_key = f"plugin_{plugin_name}"
            keys_to_remove = [k for k in sys.modules.keys() if k.startswith(module_key)]
            for key in keys_to_remove:
                del sys.modules[key]

            # Перезагружаем
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_key, str(module_path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_key] = module
            spec.loader.exec_module(module)

            # Пересоздаём экземпляр плагина
            if hasattr(module, "main"):
                new_plugin = module.main(self.app, self)
                self.instances[plugin_name] = new_plugin
                self._loaded_modules[plugin_name] = module

                # Регистрируем хуки заново
                self._register_hooks(info, new_plugin)
                # Регистрируем UI заново
                self._register_ui(info, new_plugin)

                if hasattr(self.app, '_log'):
                    self.app._log(f"✅ Плагин '{plugin_name}' перезагружен", "SYS")
                return True
            else:
                if hasattr(self.app, '_log'):
                    self.app._log(f"⚠️ Плагин '{plugin_name}': main не найден", "SYS")
                return False

        except Exception as e:
            if hasattr(self.app, '_log'):
                self.app._log(f"❌ Ошибка перезагрузки {plugin_name}: {e}", "SYS")
            import traceback
            traceback.print_exc()
            return False


def get_extended_plugin_manager(app, force_reload=False):
    """Синглтон для расширенного менеджера"""
    global _plugin_manager_instance
    if force_reload or _plugin_manager_instance is None:
        _plugin_manager_instance = ExtendedPluginManager(app)
    return _plugin_manager_instance
