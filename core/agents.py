import re
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from .mistral_client import call_mistral_agent
from .mcp_client import process_mcp_tags, call_mcp_tool, get_available_servers

# Папка с навыками (рекурсивно)
SKILLS_DIR = Path.home() / ".xli" / "skills"

def load_all_skills() -> Dict[str, str]:
    """Рекурсивно загружает все .md файлы из папки skills и подпапок"""
    skills = {}
    if SKILLS_DIR.exists():
        for skill_file in SKILLS_DIR.rglob("*.md"):
            # Пропускаем скрытые и временные файлы
            if skill_file.name.startswith('.') or skill_file.name.startswith('_'):
                continue
            # Используем относительный путь как имя
            rel_path = skill_file.relative_to(SKILLS_DIR)
            name = str(rel_path).replace('/', '_').replace('\\', '_').replace('.md', '')
            try:
                content = skill_file.read_text(encoding='utf-8')
                skills[name] = content
            except Exception as e:
                print(f"Ошибка чтения {skill_file}: {e}")
    return skills

def get_skills_context(agent_name: str, max_skills: int = 6) -> str:
    """Возвращает релевантные навыки для агента с приоритетом"""
    all_skills = load_all_skills()
    if not all_skills:
        return ""
    
    # Ключевые слова для каждого агента
    keywords = {
        "CODER": ["python", "code", "file", "script", "function", "class", "import", "pip", "git", "bash", "programming"],
        "DEBUGGER": ["error", "debug", "bug", "fix", "test", "trace", "exception", "logging", "pytest"],
        "OPTIMIZER": ["optimize", "performance", "speed", "memory", "fast", "profile", "refactor", "efficient"]
    }
    
    agent_keywords = keywords.get(agent_name, ["code"])
    
    # Оценка релевантности навыков
    scored_skills = []
    for name, content in all_skills.items():
        score = 0
        name_lower = name.lower()
        content_lower = content.lower()
        
        for kw in agent_keywords:
            if kw in name_lower:
                score += 15
            if kw in content_lower:
                score += 5
        
        # Базовые навыки всегда имеют приоритет
        if "core" in name_lower or "00" in name_lower:
            score += 20
        
        if score > 0:
            scored_skills.append((score, name, content[:2000]))
    
    # Сортировка по релевантности
    scored_skills.sort(key=lambda x: x[0], reverse=True)
    selected = scored_skills[:max_skills]
    
    if not selected:
        return ""
    
    result = "\n\n📚 **Доступные навыки (из папки skills):**\n"
    for score, name, content in selected:
        # Берём первые 600 символов каждого навыка
        short_content = content[:600] + "..." if len(content) > 600 else content
        result += f"\n### {name}\n{short_content}\n"
    
    return result

def run_shell_command(cmd: str) -> str:
    """Выполняет shell команду и возвращает вывод"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0:
            return f"✅ exit {result.returncode}\n{stdout}" if stdout else f"✅ exit {result.returncode}"
        else:
            return f"❌ exit {result.returncode}\n{stderr or stdout}"
    except subprocess.TimeoutExpired:
        return "❌ Таймаут выполнения команды (30 сек)"
    except Exception as e:
        return f"❌ Ошибка выполнения: {e}"

def execute_commands_in_text(text: str) -> str:
    """Находит и выполняет все команды в тегах <run>"""
    matches = re.findall(r'<run>(.*?)</run>', text, re.DOTALL)
    results = []
    for cmd in matches:
        cmd = cmd.strip()
        if cmd:
            out = run_shell_command(cmd)
            results.append(f"$ {cmd}\n{out}")
    return "\n\n".join(results) if results else ""

def clean_agent_response(response: str) -> str:
    """Очищает ответ агента от markdown и лишних тегов"""
    # Конвертируем markdown код в <run>
    response = re.sub(r'```(?:python|bash|sh|shell)?\n(.*?)```', r'<run>\1</run>', response, flags=re.DOTALL)
    # Убираем оставшиеся ```
    response = re.sub(r'```', '', response)
    # Убираем MCP теги (пока не используем)
    response = re.sub(r'<mcp:\w+_[^>]*>.*?</mcp:\w+_[^>]*>', '', response, flags=re.DOTALL)
    # Преобразуем **жирный** в обычный текст
    response = re.sub(r'\*\*(.*?)\*\*', r'\1', response)
    return response

async def think_with_sequential(agent, task: str, context: str = "") -> str:
    """Использует sequential thinking MCP для разбиения сложной задачи"""
    servers = get_available_servers()
    if "sequential_thinking" not in servers:
        return await agent._think_direct(task, context)
    
    try:
        think_result = call_mcp_tool("sequential_thinking", "sequentialthinking", {
            "thought": f"Разбей задачу на логические шаги:\n{task}\nКонтекст: {context}",
            "thoughtNumber": 1,
            "totalThoughts": 1,
            "nextThoughtNeeded": True
        })
        
        if "error" not in think_result.lower() and len(think_result) > 50:
            enhanced_task = f"{task}\n\n📋 План действий (разбивка на шаги):\n{think_result[:800]}\n\nВыполни каждый шаг последовательно."
            agent._log_think(f"Sequential thinking: {think_result[:200]}")
            return await agent._think_direct(enhanced_task, context)
    except Exception as e:
        print(f"Sequential thinking error: {e}")
    
    return await agent._think_direct(task, context)

class XliAgent:
    def __init__(self, name: str, agent_id: str, role: str, use_sequential_thinking: bool = True):
        self.name = name
        self.agent_id = agent_id
        self.role = role
        self.history = []
        self.use_sequential_thinking = use_sequential_thinking
        self.debug_logs = []

    def _log_think(self, msg: str):
        """Внутреннее логирование для отладки"""
        self.debug_logs.append(msg)
        if len(self.debug_logs) > 20:
            self.debug_logs = self.debug_logs[-20:]

    async def _think_direct(self, task: str, context: str = "") -> str:
        # Загружаем релевантные навыки
        skills_context = get_skills_context(self.name)
        
        # Формируем системный промпт с навыками
        enhanced_role = self.role + f"""
        
{skills_context}

**ВАЖНЫЕ ПРАВИЛА ФОРМАТИРОВАНИЯ:**
- НЕ ИСПОЛЬЗУЙ ``` (три кавычки) для кода
- НЕ ИСПОЛЬЗУЙ маркдаун (кроме **жирного**)
- Команды ОБЯЗАТЕЛЬНО оборачивай в <run>тег</run>
- Используй ПОЛНЫЕ ПУТИ к файлам: /data/data/com.termux/files/home/...
- Пример: <run>python3 /data/data/com.termux/files/home/test.py</run>

**Твоя задача:**
1. Проанализируй запрос пользователя
2. Напиши необходимый код
3. Создай файлы через <run>echo "..." > /путь/к/файлу</run>
4. Запусти скрипт через <run>python3 /полный/путь/к/файлу.py</run>
5. Будь краток, но информативен"""

        messages = [{"role": "system", "content": enhanced_role}]
        
        # Добавляем историю (последние 10 сообщений)
        for msg in self.history[-10:]:
            messages.append(msg)
        
        # Добавляем контекст от других агентов
        if context:
            messages.append({"role": "user", "content": f"📋 КОНТЕКСТ ОТ ДРУГИХ АГЕНТОВ:\n{context}"})
        
        # Добавляем текущую задачу
        messages.append({"role": "user", "content": task})

        # Вызов API
        raw_response = await call_mistral_agent(self.agent_id, messages, temperature=0.4)
        
        # Очистка ответа
        cleaned = clean_agent_response(raw_response)
        
        # Обработка MCP тегов (если остались)
        processed = process_mcp_tags(cleaned)
        
        # Выполнение команд
        output = execute_commands_in_text(processed)

        # Сохраняем в историю
        self.history.append({"role": "user", "content": task})
        self.history.append({"role": "assistant", "content": processed})

        # Если есть вывод команд, добавляем его в ответ
        if output:
            return f"{processed}\n\n📦 РЕЗУЛЬТАТ ВЫПОЛНЕНИЯ:\n{output}"
        return processed

    async def think(self, task: str, context: str = "") -> str:
        """
        Основной метод для вызова агента.
        Автоматически определяет, нужно ли использовать sequential thinking.
        """
        # Определяем сложность задачи
        is_complex = (
            self.use_sequential_thinking and 
            ("сложн" in task.lower() or 
             "разбей" in task.lower() or 
             "много" in task.lower() or
             "план" in task.lower() or
             len(task.split()) > 40)
        )
        
        if is_complex:
            self._log_think(f"Задача сложная, используем sequential thinking")
            return await think_with_sequential(self, task, context)
        
        return await self._think_direct(task, context)

    def get_debug_logs(self) -> List[str]:
        """Возвращает логи отладки"""
        return self.debug_logs
