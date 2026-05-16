#!/usr/bin/env python3
"""
Расширенный менеджер плагинов с горячей перезагрузкой
"""

import importlib
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from core.plugin_manager import PluginManager, get_plugin_manager


class ExtendedPluginManager(PluginManager):
    """Менеджер плагинов с поддержкой горячей перезагрузки"""
    
    def __init__(self, app):
        super().__init__(app)
        self._loaded_modules: Dict[str, Any] = {}
    
    def reload_plugin(self, plugin_name: str) -> bool:
        """Перезагрузить конкретный плагин"""
        if plugin_name not in self.plugins:
            return False
        
        # Находим модуль
        module_path = None
        for path in self.plugin_paths:
            if (path / plugin_name).exists():
                module_path = path / plugin_name
                break
            elif (path / f"{plugin_name}.py").exists():
                module_path = path / f"{plugin_name}.py"
                break
        
        if not module_path:
            return False
        
        try:
            # Выгружаем старый
            if plugin_name in self._loaded_modules:
                del self._loaded_modules[plugin_name]
            
            # Очищаем из sys.modules
            module_key = f"plugins_{plugin_name}"
            if module_key in sys.modules:
                del sys.modules[module_key]
            
            # Загружаем заново
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_key, module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_key] = module
            spec.loader.exec_module(module)
            
            # Пересоздаём экземпляр плагина
            if hasattr(module, "main"):
                old_plugin = self.plugins[plugin_name]
                new_plugin = module.main(self.app, self)
                
                # Копируем UI-виджеты из старого (если нужно)
                if hasattr(old_plugin, "get_panel_widget") and hasattr(new_plugin, "get_panel_widget"):
                    pass  # UI будет пересоздан отдельно
                
                self.plugins[plugin_name] = new_plugin
                self._loaded_modules[plugin_name] = module
                
                self.app._log(f"✅ Плагин '{plugin_name}' перезагружен", "SYS")
                return True
        except Exception as e:
            self.app._log(f"❌ Ошибка перезагрузки {plugin_name}: {e}", "SYS")
            return False


def get_extended_plugin_manager(app, force_reload=False):
    """Синглтон для расширенного менеджера"""
    global _plugin_manager_instance
    if force_reload or _plugin_manager_instance is None:
        _plugin_manager_instance = ExtendedPluginManager(app)
    return _plugin_manager_instance
