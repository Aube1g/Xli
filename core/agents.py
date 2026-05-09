import re
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any
from .mistral_client import call_mistral_agent
from .mcp_client import process_mcp_tags, call_mcp_tool, get_available_servers

SKILLS_DIR = Path.home() / ".xli" / "skills"

# MCP роутинг: какой сервер за что отвечает
MCP_ROUTING = {
    "coder": {
        "pre": ["knowledge_base"],      # Перед кодингом — поиск по коду
        "post": ["auto_tester"],         # После — запуск тестов
    },
    "debugger": {
        "pre": ["debugger"],             # Анализ ошибок через MCP
        "post": ["auto_tester"],         # Проверка фикса
    },
    "optimizer": {
        "pre": ["refactor", "architecture"],  # Анализ сложности
        "post": ["auto_tester"],              # Проверка после оптимизации
    }
}

def load_all_skills() -> Dict[str, str]:
    skills = {}
    if SKILLS_DIR.exists():
        for skill_file in SKILLS_DIR.rglob("*.md"):
            if skill_file.name.startswith('.') or skill_file.name.startswith('_'):
                continue
            rel_path = skill_file.relative_to(SKILLS_DIR)
            name = str(rel_path).replace('/', '_').replace('\\', '_').replace('.md', '')
            try:
                content = skill_file.read_text(encoding='utf-8')
                skills[name] = content
            except Exception as e:
                print(f"Ошибка чтения {skill_file}: {e}")
    return skills

def get_skills_context(agent_name: str, max_skills: int = 6) -> str:
    all_skills = load_all_skills()
    if not all_skills:
        return ""

    keywords = {
        "CODER": ["python", "code", "file", "script", "function", "class", "import", "pip", "git", "bash"],
        "DEBUGGER": ["error", "debug", "bug", "fix", "test", "trace", "exception", "logging", "pytest"],
        "OPTIMIZER": ["optimize", "performance", "speed", "memory", "fast", "profile", "refactor", "efficient"]
    }

    agent_keywords = keywords.get(agent_name, ["code"])
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
        if "core" in name_lower or "00" in name_lower:
            score += 20
        if score > 0:
            scored_skills.append((score, name, content[:2000]))

    scored_skills.sort(key=lambda x: x[0], reverse=True)
    selected = scored_skills[:max_skills]

    if not selected:
        return ""

    result = "\n\n📚 **Доступные навыки:**\n"
    for score, name, content in selected:
        short_content = content[:600] + "..." if len(content) > 600 else content
        result += f"\n### {name}\n{short_content}\n"
    return result

def run_shell_command(cmd: str) -> str:
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
    matches = re.findall(r'<run>(.*?)</run>', text, re.DOTALL)
    results = []
    for cmd in matches:
        cmd = cmd.strip()
        if cmd:
            out = run_shell_command(cmd)
            results.append(f"$ {cmd}\n{out}")
    return "\n\n".join(results) if results else ""

def clean_agent_response(response: str) -> str:
    response = re.sub(r'```(?:python|bash|sh|shell)?\n(.*?)```', r'\1', response, flags=re.DOTALL)
    response = re.sub(r'```', '', response)
    response = re.sub(r'<mcp>.*?</mcp>', '', response, flags=re.DOTALL)
    response = re.sub(r'\*\*(.*?)\*\*', r'\1', response)
    return response

async def run_mcp_pre_step(agent_name: str, task: str) -> str:
    """Запускает MCP pre-шаги для агента"""
    servers = get_available_servers()
    routing = MCP_ROUTING.get(agent_name.lower(), {})
    pre_servers = routing.get("pre", [])
    
    context_parts = []
    
    for server_name in pre_servers:
        if server_name not in servers:
            continue
            
        server = servers[server_name]
        tools = server.get("tools", [])
        
        if not tools:
            continue
            
        # Выбираем первый доступный инструмент
        tool = tools[0]
        
        try:
            result = call_mcp_tool(server_name, tool, {
                "query": task,
                "code": task,
            })
            if result and "error" not in result.lower():
                context_parts.append(f"[{server_name}] {result[:500]}")
        except Exception as e:
            print(f"MCP pre-step error {server_name}: {e}")
    
    return "\n\n".join(context_parts) if context_parts else ""

async def run_mcp_post_step(agent_name: str, code: str) -> str:
    """Запускает MCP post-шаги для агента"""
    servers = get_available_servers()
    routing = MCP_ROUTING.get(agent_name.lower(), {})
    post_servers = routing.get("post", [])
    
    results = []
    
    for server_name in post_servers:
        if server_name not in servers:
            continue
            
        server = servers[server_name]
        tools = server.get("tools", [])
        
        if not tools:
            continue
            
        tool = tools[0]
        
        try:
            result = call_mcp_tool(server_name, tool, {
                "code": code,
                "test_code": code,
            })
            if result and "error" not in result.lower():
                results.append(f"[{server_name}] {result[:500]}")
        except Exception as e:
            print(f"MCP post-step error {server_name}: {e}")
    
    return "\n\n".join(results) if results else ""

class XliAgent:
    def __init__(self, name: str, agent_id: str, role: str, use_sequential_thinking: bool = True):
        self.name = name
        self.agent_id = agent_id
        self.role = role
        self.history = []
        self.use_sequential_thinking = use_sequential_thinking
        self.debug_logs = []

    def _log_think(self, msg: str):
        self.debug_logs.append(msg)
        if len(self.debug_logs) > 20:
            self.debug_logs = self.debug_logs[-20:]

    async def _think_direct(self, task: str, context: str = "") -> str:
        skills_context = get_skills_context(self.name)

        enhanced_role = self.role + f"""

{skills_context}

**ВАЖНЫЕ ПРАВИЛА ФОРМАТИРОВАНИЯ:**
- НЕ ИСПОЛЬЗУЙ ``` (три кавычки) для кода
- НЕ ИСПОЛЬЗУЙ маркдаун (кроме **жирного**)
- Команды ОБЯЗАТЕЛЬНО оборачивай в <run>тег</run>
- Используй ПОЛНЫЕ ПУТИ к файлам: /data/data/com.termux/files/home/...
- Пример: python3 /data/data/com.termux/files/home/test.py

**Твоя задача:**
1. Проанализируй запрос
2. Напиши необходимый код
3. Создай файлы через echo "..." > /путь/к/файлу
4. Запусти скрипт через python3 /полный/путь/к/файлу.py
5. Будь краток, но информативен"""

        messages = [{"role": "system", "content": enhanced_role}]

        for msg in self.history[-10:]:
            messages.append(msg)

        if context:
            messages.append({"role": "user", "content": f"📋 КОНТЕКСТ ОТ ДРУГИХ АГЕНТОВ:\n{context}"})

        messages.append({"role": "user", "content": task})

        raw_response = await call_mistral_agent(self.agent_id, messages, temperature=0.4)
        cleaned = clean_agent_response(raw_response)
        processed = process_mcp_tags(cleaned)
        output = execute_commands_in_text(processed)

        self.history.append({"role": "user", "content": task})
        self.history.append({"role": "assistant", "content": processed})

        if output:
            return f"{processed}\n\n📦 РЕЗУЛЬТАТ ВЫПОЛНЕНИЯ:\n{output}"
        return processed

    async def think(self, task: str, context: str = "", use_mcp: bool = True) -> str:
        """
        Основной метод. Автоматически определяет MCP-шаги.
        """
        # Pre-step MCP
        mcp_context = ""
        if use_mcp:
            mcp_context = await run_mcp_pre_step(self.name, task)
            if mcp_context:
                self._log_think(f"MCP pre-context: {mcp_context[:200]}")
                task = f"{task}\n\n📊 MCP Анализ:\n{mcp_context}"

        # Основной вызов
        response = await self._think_direct(task, context)

        # Post-step MCP
        if use_mcp:
            post_result = await run_mcp_post_step(self.name, response)
            if post_result:
                self._log_think(f"MCP post-result: {post_result[:200]}")
                response += f"\n\n📊 MCP Проверка:\n{post_result}"

        return response

    def get_debug_logs(self) -> List[str]:
        return self.debug_logs

