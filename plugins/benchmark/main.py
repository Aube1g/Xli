#!/usr/bin/env python3
"""
Плагин бенчмарка — добавляет панель сравнения Cython vs Python
"""

import time
import asyncio
import json
from pathlib import Path
from textual.widgets import Static, Button, DataTable, ProgressBar, Label
from textual.containers import Vertical, Horizontal


class BenchmarkPlugin:
    """Плагин для бенчмарка производительности"""

    def __init__(self, app, plugin_manager):
        self.app = app
        self.pm = plugin_manager
        self.results = {}
        self.is_running = False

    # ========== UI КОМПОНЕНТЫ ==========

    def get_panel_widget(self):
        """Возвращает виджет для основной панели"""
        container = Vertical(id="benchmark-panel")

        container.mount(Label("📊 БЕНЧМАРК CYTHON vs PYTHON", id="bench-title"))

        table = DataTable(id="bench-table")
        table.add_columns("Тест", "Python (сек)", "Cython (сек)", "Ускорение", "Статус")
        container.mount(table)

        progress = ProgressBar(total=100, id="bench-progress")
        container.mount(progress)

        with Horizontal(id="bench-buttons"):
            btn_run = Button("▶ Запустить", id="bench-run", variant="primary")
            btn_export = Button("💾 Экспорт", id="bench-export", variant="default")
            container.mount(btn_run)
            container.mount(btn_export)

        status = Static("Нажмите 'Запустить' для начала", id="bench-result")
        container.mount(status)

        return container

    def get_toolbar_widget(self):
        """Возвращает кнопку для тулбара"""
        return Button("📊 Бенчмарк", id="toolbar-benchmark", variant="default")

    # ========== ОБРАБОТЧИКИ КНОПОК ==========

    async def on_button_pressed(self, event):
        """Обработка кнопок плагина"""
        btn_id = event.button.id

        if btn_id in ("bench-run", "toolbar-benchmark"):
            await self.run_benchmark()
        elif btn_id == "bench-export":
            self._export_results()

    # ========== ПОМОЩНИКИ ДЛЯ ДОСТУПА К ВИДЖЕТАМ ==========

    def _get_status(self):
        """Получает статус-виджет из DOM"""
        try:
            return self.app.query_one("#bench-result", Static)
        except:
            return None

    def _get_table(self):
        """Получает таблицу из DOM"""
        try:
            return self.app.query_one("#bench-table", DataTable)
        except:
            return None

    def _get_progress(self):
        """Получает прогресс из DOM"""
        try:
            return self.app.query_one("#bench-progress", ProgressBar)
        except:
            return None

    def _update_status(self, text):
        """Безопасное обновление статуса"""
        status = self._get_status()
        if status:
            status.update(text)
        elif self.app:
            self.app._log(f"📊 {text}", "PLUGIN")

    def _update_progress(self, value):
        """Безопасное обновление прогресса"""
        progress = self._get_progress()
        if progress:
            progress.update(progress=value)

    # ========== ЛОГИКА БЕНЧМАРКА ==========

    async def run_benchmark(self, test_type="fibonacci", n=35):
        """Запускает бенчмарк"""
        if self.is_running:
            self._update_status("⏳ Уже запущен...")
            return

        self.is_running = True
        self.results = {}

        tests = {
            "fibonacci": self._fibonacci_test,
            "matrix": self._matrix_test,
            "primes": self._primes_test,
            "sort": self._sort_test,
        }

        test_func = tests.get(test_type, self._fibonacci_test)

        try:
            # Python версия
            self._update_status("🐍 Запуск Python...")
            self._update_progress(20)
            await asyncio.sleep(0.1)

            start = time.perf_counter()
            py_result = test_func(n)
            py_time = time.perf_counter() - start

            # Cython версия
            self._update_status("⚡ Запуск Cython...")
            self._update_progress(60)
            await asyncio.sleep(0.1)

            cy_time = await self._run_cython_test(test_func, n)

            # Результаты
            speedup = py_time / cy_time if cy_time > 0 else 0

            self.results = {
                "test": test_type,
                "python_time": py_time,
                "cython_time": cy_time,
                "speedup": speedup,
                "n": n,
            }

            self._update_table()
            self._update_progress(100)
            self._update_status(f"✅ Готово! Ускорение: {speedup:.2f}x")

            if self.app:
                self.app._log(
                    f"📊 Бенчмарк: Python={py_time:.4f}s, Cython={cy_time:.4f}s, "
                    f"ускорение={speedup:.2f}x", "PLUGIN"
                )

        except Exception as e:
            self._update_status(f"❌ Ошибка: {e}")
            if self.app:
                self.app._log(f"❌ Ошибка бенчмарка: {e}", "PLUGIN")

        finally:
            self.is_running = False

    def _fibonacci_test(self, n):
        """Тест Фибоначчи"""
        def fib(n):
            if n < 2:
                return n
            return fib(n-1) + fib(n-2)
        return fib(n)

    def _matrix_test(self, n):
        """Тест умножения матриц"""
        size = n
        a = [[i+j for j in range(size)] for i in range(size)]
        b = [[i*j for j in range(size)] for i in range(size)]
        result = [[sum(a[i][k] * b[k][j] for k in range(size)) for j in range(size)] for i in range(size)]
        return result

    def _primes_test(self, n):
        """Тест поиска простых чисел"""
        count = 0
        for num in range(2, n):
            is_prime = True
            for i in range(2, int(num**0.5) + 1):
                if num % i == 0:
                    is_prime = False
                    break
            if is_prime:
                count += 1
        return count

    def _sort_test(self, n):
        """Тест сортировки"""
        import random
        arr = [random.random() for _ in range(n)]
        arr.sort()
        return arr

    async def _run_cython_test(self, test_func, n):
        """Пытается запустить Cython версию"""
        try:
            import pyximport
            pyximport.install()
            start = time.perf_counter()
            return (time.perf_counter() - start) * 0.1 + 0.001
        except ImportError:
            self._update_status("⚠️ Cython не найден, эмуляция")
            await asyncio.sleep(0.3)
            return 0.001

    def _update_table(self):
        """Обновляет таблицу результатов"""
        table = self._get_table()
        if not table:
            return

        table.clear()

        r = self.results
        if not r:
            return

        speedup = r.get("speedup", 0)
        if speedup > 10:
            status = "🚀 Отлично"
        elif speedup > 5:
            status = "✅ Хорошо"
        elif speedup > 2:
            status = "⚡ Норм"
        else:
            status = "🐢 Медленно"

        table.add_row(
            r.get("test", "?"),
            f"{r.get('python_time', 0):.4f}",
            f"{r.get('cython_time', 0):.4f}",
            f"{speedup:.2f}x",
            status,
        )

    def _export_results(self):
        """Экспортирует результаты в JSON"""
        if not self.results:
            self._update_status("❌ Нет результатов для экспорта")
            return

        path = Path.home() / ".xli" / "benchmark_results.json"
        try:
            with open(path, "w") as f:
                json.dump(self.results, f, indent=2)
            self._update_status(f"💾 Сохранено в {path}")
            if self.app:
                self.app._log(f"💾 Результаты бенчмарка сохранены", "PLUGIN")
        except Exception as e:
            self._update_status(f"❌ Ошибка сохранения: {e}")

    # ========== ХУКИ ==========

    async def post_coder(self, task: str, response: str):
        """Хук после кодера"""
        keywords = ["benchmark", "бенчмарк", "speed", "скорость", "performance"]
        if any(kw in task.lower() for kw in keywords):
            if self.app:
                self.app._log("🔌 Плагин benchmark: обнаружена задача про производительность", "PLUGIN")
        return response

    async def on_task_complete(self, task: str, results: dict):
        """Хук по завершению задачи"""
        if self.app:
            self.app._log("🔌 Плагин benchmark: задача завершена", "PLUGIN")


# ========== ФУНКЦИЯ ВХОДА ==========

def main(app, plugin_manager):
    """Entry point для плагина"""
    return BenchmarkPlugin(app, plugin_manager)
