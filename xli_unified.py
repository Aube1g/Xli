#!/usr/bin/env python3
"""
XLI PRO ULTIMATE v3 — Unified Entry Point + FULL ERROR LOGGING
Auto-detect: TUI (textual) -> Neovim (pynvim) -> Headless (fallback)

v3 CHANGES:
- Structured logging (JSONL)
- Full error capture in all operations
- Nvim bridge connection logging
- Shell command exit code logging
- File operation error logging
- Agent chain step logging
- Questionnaire error logging
- Global exception hook
"""

import asyncio
import sys
import argparse
import os
import json
import re
import subprocess
import traceback
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

# --- PATH SETUP ---
XLI_DIR = Path.home() / ".xli"
sys.path.insert(0, str(XLI_DIR))

# --- AUTO-DETECT MODE ---
HAS_TEXTUAL = False
HAS_PYNVIM = False
NVIM_LISTEN = None

try:
    import textual
    from textual.app import App
    from textual.containers import Container, Horizontal, Vertical, Grid, ScrollableContainer
    from textual.widgets import Header, Footer, Button, Static, Input, Collapsible, ProgressBar
    from rich.text import Text
    from rich.console import Console
    from rich.panel import Panel
    from pyfiglet import Figlet
    HAS_TEXTUAL = True
except ImportError as e:
    pass

try:
    import pynvim
    HAS_PYNVIM = True
    NVIM_LISTEN = os.environ.get('NVIM_LISTEN_ADDRESS')
    if not NVIM_LISTEN and 'NVIM' in os.environ:
        for sock in ['/tmp/nvim', str(Path.home() / '.local/share/nvim/server.pipe')]:
            if Path(sock).exists():
                NVIM_LISTEN = sock
                break
except ImportError:
    pass

# --- CORE IMPORTS ---
try:
    from core.mistral_client import AGENT_IDS, call_mistral_agent
    from core.mcp_client import get_available_servers, list_mcp_servers, toggle_mcp_server, process_mcp_tags
    from core.agents import XliAgent, load_all_skills, get_skills_context, run_mcp_pre_step, run_mcp_post_step, clean_agent_response, execute_commands_in_text
except ImportError as e:
    print("ERROR: Cannot import core modules: %s" % e)
    sys.exit(1)

# --- STRUCTURED LOGGER ---
class StructuredLogger:
    """Structured logging with multiple outputs"""
    def __init__(self, name: str):
        self.name = name
        self.log_dir = XLI_DIR / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        import logging
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] %(message)s",
            datefmt="%H:%M:%S"
        )

        # All logs
        fh = logging.FileHandler(self.log_dir / "xli.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        # Errors only
        eh = logging.FileHandler(self.log_dir / "errors.log", encoding="utf-8")
        eh.setLevel(logging.ERROR)
        eh.setFormatter(formatter)
        self.logger.addHandler(eh)

        # Structured JSONL
        self.structured_path = self.log_dir / "structured.log"

        # Console if not in nvim
        if not (HAS_PYNVIM and NVIM_LISTEN):
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.INFO)
            ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self.logger.addHandler(ch)

        self._error_count = 0
        self._setup_global_hook()

    def _setup_global_hook(self):
        """Catch uncaught exceptions"""
        original = sys.excepthook
        def hook(exc_type, exc_val, exc_tb):
            self.log_structured("CRITICAL", "uncaught",
                "Uncaught: %s: %s" % (exc_type.__name__, exc_val),
                exc_info="".join(traceback.format_exception(exc_type, exc_val, exc_tb)))
            original(exc_type, exc_val, exc_tb)
        sys.excepthook = hook

    def log_structured(self, level: str, component: str, message: str,
                       details: Optional[Dict] = None, exc_info: Optional[str] = None):
        """Write structured JSONL log"""
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "level": level,
            "component": component,
            "message": message,
        }
        if details:
            entry["details"] = details
        if exc_info:
            entry["trace"] = exc_info
        try:
            with open(self.structured_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception as e:
            self.logger.error("Failed to write structured log: %s" % e)

        # Also to standard logger
        method = getattr(self.logger, level.lower(), self.logger.info)
        method("[%s] %s" % (component, message))

    def log_error(self, component: str, message: str, exc: Optional[Exception] = None,
                  details: Optional[Dict] = None):
        """Unified error logging"""
        self._error_count += 1
        exc_str = traceback.format_exc() if exc else None
        self.log_structured("ERROR", component, message, details, exc_str)
        self.logger.error("[%s] %s" % (component, message), exc_info=exc is not None)

    def log_nvim_error(self, source: str, message: str, details: Optional[Dict] = None):
        """Log nvim-side errors to shared file"""
        self.log_structured("ERROR", "nvim.%s" % source, message, details)
        nvim_err = self.log_dir / "nvim_errors.log"
        ts = datetime.now().strftime("%H:%M:%S")
        line = "[%s] [%s] %s" % (ts, source, message)
        if details:
            line += " | %s" % json.dumps(details, ensure_ascii=False, default=str)
        try:
            with open(nvim_err, 'a', encoding='utf-8') as f:
                f.write(line + "\n")
        except Exception as e:
            self.logger.error("Failed to write nvim error: %s" % e)

# Initialize logger
slog = StructuredLogger("xli")
logger = slog.logger


# --- ENVIRONMENT ADAPTER v3 ---

class EnvironmentAdapter:
    def __init__(self):
        self.name = self._detect_mode()
        self.home = str(Path.home())
        self.cwd = os.getcwd()
        self.is_termux = '/data/data/com.termux' in self.home
        self.nvim = None
        self._connection_errors = []
        slog.log_structured("INFO", "env", "EnvironmentAdapter initializing", {
            "mode": self.name,
            "cwd": self.cwd,
            "termux": self.is_termux
        })
        if self.name == "neovim" and HAS_PYNVIM:
            self._connect_nvim()
        slog.log_structured("INFO", "env", "EnvironmentAdapter ready", {
            "mode": self.name,
            "nvim_connected": self.nvim is not None
        })

    def _detect_mode(self) -> str:
        if HAS_PYNVIM and NVIM_LISTEN:
            slog.log_structured("DEBUG", "env", "Detected neovim mode", {"listen": NVIM_LISTEN})
            return "neovim"
        if HAS_TEXTUAL:
            slog.log_structured("DEBUG", "env", "Detected terminal mode")
            return "terminal"
        slog.log_structured("DEBUG", "env", "Detected headless mode")
        return "headless"

    def _connect_nvim(self):
        slog.log_structured("INFO", "nvim", "Connecting to Neovim...")
        try:
            if NVIM_LISTEN and Path(NVIM_LISTEN).exists():
                slog.log_structured("DEBUG", "nvim", "Trying socket", {"path": NVIM_LISTEN})
                self.nvim = pynvim.attach('socket', path=NVIM_LISTEN)
                slog.log_structured("INFO", "nvim", "Connected via socket", {"path": NVIM_LISTEN})
                return
            elif 'NVIM' in os.environ:
                slog.log_structured("DEBUG", "nvim", "Trying child connection")
                self.nvim = pynvim.attach('child', argv=sys.argv)
                slog.log_structured("INFO", "nvim", "Connected via child")
                return
        except Exception as e:
            err_msg = "Neovim connect failed: %s" % e
            slog.log_error("nvim", err_msg, exc=e)
            self._connection_errors.append(err_msg)

        # Try additional socket paths
        for sock in ['/tmp/nvim', '/data/data/com.termux/files/usr/tmp/nvim',
                     str(Path.home() / '.local/share/nvim/server.pipe')]:
            if Path(sock).exists():
                try:
                    slog.log_structured("DEBUG", "nvim", "Trying fallback socket", {"path": sock})
                    self.nvim = pynvim.attach('socket', path=sock)
                    slog.log_structured("INFO", "nvim", "Connected via fallback", {"path": sock})
                    return
                except Exception as e:
                    slog.log_error("nvim", "Fallback socket failed: %s" % sock, exc=e)
                    self._connection_errors.append("%s: %s" % (sock, e))

        slog.log_structured("ERROR", "nvim", "All connection methods exhausted",
                           {"errors": self._connection_errors})

    def is_nvim(self) -> bool:
        return self.name == "neovim" and self.nvim is not None

    def notify(self, msg: str, level: str = "info"):
        slog.log_structured("INFO", "notify", "Notify [%s]: %s" % (level, msg[:100]))
        if self.is_nvim():
            try:
                level_map = {"info": 2, "warn": 3, "warning": 3, "error": 4}
                self.nvim.call('vim.notify', msg, level_map.get(level, 2), {
                    'title': 'FIRE XLI', 'timeout': 3000
                })
                slog.log_structured("DEBUG", "notify", "nvim.notify sent")
                return
            except Exception as e:
                slog.log_error("notify", "nvim.notify failed: %s" % e, exc=e)
        print("[%s] %s" % (level.upper(), msg))

    def run_shell(self, cmd: str, timeout: int = 30) -> str:
        slog.log_structured("INFO", "shell", "Executing: %s" % cmd[:100],
                           {"timeout": timeout, "cwd": self.cwd})
        dangerous = ['rm -rf /', 'mkfs', 'dd if=', '>:(){ :|:& };:',
                     'chmod 777 /', 'mv /*', 'cp /*', 'curl .*| sh', 'wget .*| sh']
        cmd_lower = cmd.lower()
        for d in dangerous:
            if d in cmd_lower:
                slog.log_structured("WARN", "shell", "Dangerous command blocked", {"cmd": cmd[:50]})
                self.notify("WARNING Dangerous command blocked: %s" % cmd[:50], "warn")
                return "BLOCKED (dangerous): %s" % cmd

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True,
                text=True, timeout=timeout, cwd=self.cwd)
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            slog.log_structured("DEBUG", "shell", "Command finished",
                               {"exit_code": result.returncode,
                                "stdout_len": len(stdout),
                                "stderr_len": len(stderr)})
            if result.returncode == 0:
                return "OK exit %d\n%s" % (result.returncode, stdout) if stdout else "OK exit %d" % result.returncode
            slog.log_error("shell", "Command failed: exit %d" % result.returncode,
                          details={"cmd": cmd[:100], "stderr": stderr[:500]})
            return "FAIL exit %d\n%s" % (result.returncode, stderr or stdout)
        except subprocess.TimeoutExpired:
            slog.log_error("shell", "Command timeout after %ds" % timeout,
                          details={"cmd": cmd[:100]})
            return "TIMEOUT after %ds" % timeout
        except Exception as e:
            slog.log_error("shell", "Command execution failed", exc=e,
                          details={"cmd": cmd[:100]})
            return "ERROR: %s" % e

    def write_file(self, path: str, content: str) -> str:
        slog.log_structured("INFO", "file", "Writing: %s" % path,
                           {"content_len": len(content)})
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding='utf-8')
            slog.log_structured("INFO", "file", "File written", {"path": path, "size": len(content)})
            return "OK File: %s" % path
        except Exception as e:
            slog.log_error("file", "Write failed: %s" % path, exc=e)
            return "ERROR: %s" % e

    def open_buffer(self, content: List[str], name: str = "XLI",
                    filetype: str = "markdown", float_win: bool = False):
        slog.log_structured("INFO", "buffer", "Opening buffer", {
            "name": name,
            "lines": len(content),
            "float": float_win
        })
        if not self.is_nvim():
            slog.log_structured("DEBUG", "buffer", "Not in nvim, printing to stdout")
            print("\n=== %s ===" % name)
            print("\n".join(content))
            return
        try:
            buf = self.nvim.api.create_buf(False, True)
            buf.name = "xli://%s" % name
            buf.options['filetype'] = filetype
            buf.options['buftype'] = 'nofile'
            buf.options['bufhidden'] = 'hide'
            buf[:] = content
            if float_win:
                editor_w = self.nvim.options['columns']
                editor_h = self.nvim.options['lines']
                width = min(100, editor_w - 4)
                height = min(30, editor_h - 4)
                win = self.nvim.api.open_win(buf, True, {
                    'relative': 'editor',
                    'row': (editor_h - height) // 2,
                    'col': (editor_w - width) // 2,
                    'width': width,
                    'height': height,
                    'style': 'minimal',
                    'border': 'rounded',
                    'title': ' %s ' % name,
                    'title_pos': 'center',
                })
                self.nvim.api.buf_set_keymap(buf.number, 'n', 'q', ':q<CR>',
                    {'noremap': True, 'silent': True})
                slog.log_structured("DEBUG", "buffer", "Float window opened", {"win": win})
            else:
                self.nvim.command('vsplit')
                win = self.nvim.current.window
                win.buffer = buf
                win.options['wrap'] = True
                win.options['cursorline'] = True
                slog.log_structured("DEBUG", "buffer", "Split buffer opened")
        except Exception as e:
            slog.log_error("buffer", "Open buffer failed", exc=e)
            print("\n=== %s ===" % name)
            print("\n".join(content))

    def get_current_file(self) -> str:
        if self.is_nvim():
            try:
                path = self.nvim.current.buffer.name
                slog.log_structured("DEBUG", "file", "Current file: %s" % path)
                return path
            except Exception as e:
                slog.log_error("file", "get_current_file failed", exc=e)
        return ""

    def get_selection(self) -> str:
        if not self.is_nvim():
            return ""
        try:
            old_reg = self.nvim.call('getreg', '"')
            old_type = self.nvim.call('getregtype', '"')
            self.nvim.command('normal! gv"xy')
            sel = self.nvim.call('getreg', 'x')
            self.nvim.call('setreg', '"', old_reg, old_type)
            slog.log_structured("DEBUG", "selection", "Got selection", {"len": len(sel)})
            return sel
        except Exception as e:
            slog.log_error("selection", "get_selection failed", exc=e)
            return ""

    def append_history(self, task: str, result: str = "", agent: str = ""):
        hist_file = XLI_DIR / "history.txt"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = "[%s] [%s] %s" % (timestamp, agent, task)
        if result:
            entry += "\n  -> %s" % result[:200]
        try:
            with open(hist_file, 'a', encoding='utf-8') as f:
                f.write(entry + "\n")
            slog.log_structured("DEBUG", "history", "Appended", {"task": task[:50]})
        except Exception as e:
            slog.log_error("history", "Append failed", exc=e)

    def get_history(self, lines: int = 50) -> List[str]:
        hist_file = XLI_DIR / "history.txt"
        if not hist_file.exists():
            return []
        try:
            with open(hist_file, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
            result = [l.strip() for l in all_lines[-lines:] if l.strip()]
            slog.log_structured("DEBUG", "history", "Read %d lines" % len(result))
            return result
        except Exception as e:
            slog.log_error("history", "Read failed", exc=e)
            return []

    def get_system_context(self) -> str:
        lines = ["\nTARGET CONTEXT:"]
        lines.append("- Env: %s" % self.name.upper())
        lines.append("- CWD: %s" % self.cwd)
        lines.append("- Home: %s" % self.home)
        if self.is_termux:
            lines.append("- Platform: Termux (Android)")
            lines.append("- Packages: pkg install")
            lines.append("- Python: python3")
            lines.append("- Storage: ~/storage/")
        if self.name == "neovim":
            lines.append("\nNEOVIM MODE:")
            lines.append("- NO textual/tui")
            lines.append("- Commands in <SHELL>tags</SHELL>")
            lines.append("- Files: <SHELL>echo '...' > /full/path</SHELL>")
            lines.append("- Result: text in response")
        elif self.name == "terminal":
            lines.append("\nTERMINAL MODE:")
            lines.append("- Full TUI available")
        else:
            lines.append("\nHEADLESS MODE:")
            lines.append("- Text output only")
        try:
            servers = get_available_servers()
            lines.append("\nAVAILABLE MCP:")
            for name, info in servers.items():
                lines.append("  OK %s: %s" % (name, info.get('description', '')[:40]))
        except Exception as e:
            slog.log_error("mcp", "get_available_servers failed", exc=e)
        return "\n".join(lines)


# --- QUESTIONNAIRE v3 ---

class Question:
    def __init__(self, id: str, question: str, type: str = "text",
                 options: Optional[List[str]] = None, default: Optional[str] = None):
        self.id = id
        self.question = question
        self.type = type
        self.options = options or []
        self.default = default


class Questionnaire:
    def __init__(self, env: EnvironmentAdapter):
        self.env = env
        self.answers: Dict[str, str] = {}

    async def run(self, questions: List[Question]) -> Dict[str, str]:
        slog.log_structured("INFO", "questionnaire", "Starting questionnaire",
                           {"questions": len(questions), "mode": self.env.name})
        if self.env.is_nvim():
            result = await self._run_nvim(questions)
        else:
            result = await self._run_terminal(questions)
        slog.log_structured("INFO", "questionnaire", "Completed",
                           {"answers": len(result)})
        return result

    async def _run_nvim(self, questions: List[Question]) -> Dict[str, str]:
        try:
            nvim = self.env.nvim
            buf = nvim.api.create_buf(False, True)
            buf.name = "xli://questionnaire"
            buf.options['buftype'] = 'prompt'
            buf.options['bufhidden'] = 'wipe'
            nvim.command('split')
            win = nvim.current.window
            win.buffer = buf
            win.height = 25
            self.answers = {}
            current = 0

            def render():
                if current >= len(questions):
                    lines = [
                        " FIRE XLI PRO — Done ",
                        "-" * 60,
                        "",
                        "OK All questions answered!",
                        "",
                        "Answers:",
                    ]
                    for q in questions:
                        lines.append("  %s: %s" % (q.question, self.answers.get(q.id, '-')))
                    lines.extend(["", "Press Enter to continue..."])
                    buf[:] = lines
                    return

                q = questions[current]
                lines = [
                    " FIRE XLI PRO — Task Clarification ",
                    "-" * 60,
                    "",
                    "Question %d/%d:" % (current + 1, len(questions)),
                    "   %s" % q.question,
                    "",
                ]
                if q.options:
                    lines.append("   Options:")
                    for i, opt in enumerate(q.options, 1):
                        marker = "OK" if self.answers.get(q.id) == opt else "  "
                        lines.append("   %s %d. %s" % (marker, i, opt))
                    lines.append("")
                    lines.append("   Press number or type answer")
                else:
                    lines.append("   Type answer:")
                    if q.default:
                        lines.append("   (default: %s)" % q.default)

                lines.extend(["", "-" * 60, " q — cancel | Enter — confirm"])
                buf[:] = lines

            render()

            nvim.api.buf_set_keymap(buf.number, 'n', '<CR>',
                ':lua _xli_q_submit()<CR>', {'noremap': True, 'silent': True})
            for i in range(1, 10):
                nvim.api.buf_set_keymap(buf.number, 'n', str(i),
                    ':lua _xli_q_select(%d)<CR>' % i, {'noremap': True, 'silent': True})
            nvim.api.buf_set_keymap(buf.number, 'n', 'q',
                ':lua _xli_q_cancel()<CR>', {'noremap': True, 'silent': True})

            import time
            while current < len(questions):
                time.sleep(0.5)
                try:
                    _ = buf.number
                except:
                    break

            return self.answers
        except Exception as e:
            slog.log_error("questionnaire", "Nvim questionnaire failed", exc=e)
            return await self._run_terminal(questions)

    async def _run_terminal(self, questions: List[Question]) -> Dict[str, str]:
        print("\n" + "=" * 60)
        print(" FIRE XLI PRO — Task Clarification ")
        print("=" * 60)

        for q in questions:
            print("\n? %s" % q.question)
            if q.options:
                for i, opt in enumerate(q.options, 1):
                    print("   %d. %s" % (i, opt))
                while True:
                    try:
                        choice = input("   Select: ").strip()
                        if not choice and q.default:
                            self.answers[q.id] = q.default
                            break
                        idx = int(choice) - 1
                        if 0 <= idx < len(q.options):
                            self.answers[q.id] = q.options[idx]
                            break
                        print("   INVALID")
                    except ValueError:
                        print("   Enter number")
            else:
                default_hint = " [%s]" % q.default if q.default else ""
                answer = input("   Answer%s: " % default_hint).strip()
                if not answer and q.default:
                    answer = q.default
                self.answers[q.id] = answer

        print("\nOK Clarification done!")
        return self.answers


async def generate_questions(task: str, agent_id: str) -> List[Question]:
    prompt = "Task: %s\n\nGenerate 2-4 clarifying questions. Reply ONLY JSON array:\n[{\"id\": \"name\", \"question\": \"text\", \"type\": \"text/choice\", \"options\": [\"opt1\", \"opt2\"], \"default\": \"default\"}]" % task

    try:
        slog.log_structured("DEBUG", "questions", "Generating questions", {"task": task[:50]})
        response = await call_mistral_agent(agent_id, [
            {"role": "system", "content": "Reply ONLY JSON array."},
            {"role": "user", "content": prompt}
        ])
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            data = json.loads(match.group())
            questions = [Question(**q) for q in data]
            slog.log_structured("INFO", "questions", "Generated %d questions" % len(questions))
            return questions
    except Exception as e:
        slog.log_error("questions", "Generation failed", exc=e)

    return [
        Question("language", "Language?", "choice", ["Python", "JavaScript", "TypeScript", "Go", "Rust"]),
        Question("framework", "Framework?", "choice", ["None", "React", "Vue", "FastAPI", "Flask"]),
        Question("details", "Extra requirements?", "text", default="None"),
    ]


# --- AGENTS v3 ---

class XliAgentV2:
    def __init__(self, name: str, agent_id: str, base_role: str, env: EnvironmentAdapter):
        self.name = name
        self.agent_id = agent_id
        self.base_role = base_role
        self.env = env
        self.history = []
        self.debug_logs = []
        slog.log_structured("DEBUG", "agent", "Agent initialized", {"name": name, "id": agent_id})

    def _build_role(self) -> str:
        return "%s\n\n%s\n\nRULES:\n- NO triple backticks for code\n- Commands in <SHELL>command</SHELL>\n- FULL PATHS: %s/...\n- Be concise but informative" % (self.base_role, self.env.get_system_context(), self.env.home)

    async def think(self, task: str, context: str = "", use_mcp: bool = True) -> str:
        slog.log_structured("INFO", "agent.%s" % self.name, "Thinking", {"task": task[:100]})
        mcp_ctx = ""
        if use_mcp:
            try:
                mcp_ctx = await run_mcp_pre_step(self.name, task)
                if mcp_ctx:
                    slog.log_structured("DEBUG", "agent.%s" % self.name, "MCP pre-step", {"ctx_len": len(mcp_ctx)})
                    task = "%s\n\nMCP:\n%s" % (task, mcp_ctx)
            except Exception as e:
                slog.log_error("agent.%s" % self.name, "MCP pre-step failed", exc=e)

        skills = ""
        try:
            skills = get_skills_context(self.name)
            if skills:
                slog.log_structured("DEBUG", "agent.%s" % self.name, "Skills loaded", {"len": len(skills)})
                task = "%s\n\n%s" % (task, skills)
        except Exception as e:
            slog.log_error("agent.%s" % self.name, "Skills load failed", exc=e)

        messages = [{"role": "system", "content": self._build_role()}]
        for msg in self.history[-10:]:
            messages.append(msg)
        if context:
            messages.append({"role": "user", "content": "CONTEXT:\n%s" % context})
        messages.append({"role": "user", "content": task})

        try:
            slog.log_structured("DEBUG", "agent.%s" % self.name, "Calling Mistral", {"msgs": len(messages)})
            raw = await call_mistral_agent(self.agent_id, messages, temperature=0.4)
            slog.log_structured("DEBUG", "agent.%s" % self.name, "Response received", {"len": len(raw)})
        except Exception as e:
            slog.log_error("agent.%s" % self.name, "Mistral call failed", exc=e)
            return "ERROR: Agent %s failed: %s" % (self.name, e)

        cleaned = clean_agent_response(raw)
        output = self._execute_shell(cleaned)

        self.history.extend([
            {"role": "user", "content": task},
            {"role": "assistant", "content": cleaned}
        ])

        self.env.append_history(task, output, self.name)

        if output:
            slog.log_structured("INFO", "agent.%s" % self.name, "Shell output", {"len": len(output)})
            return "%s\n\nRESULT:\n%s" % (cleaned, output)
        return cleaned

    def _execute_shell(self, text: str) -> str:
        matches = re.findall(r'<SHELL>(.*?)</SHELL>', text, re.DOTALL)
        results = []
        for cmd in matches:
            cmd = cmd.strip()
            if cmd:
                slog.log_structured("INFO", "agent.%s.shell" % self.name, "Executing: %s" % cmd[:80])
                out = self.env.run_shell(cmd)
                results.append("$ %s\n%s" % (cmd, out))
        return "\n\n".join(results) if results else ""


# --- MAIN LOGIC v3 ---

class XliCore:
    def __init__(self, env: EnvironmentAdapter):
        self.env = env
        self.agents = {
            "coder": XliAgentV2("CODER", AGENT_IDS["coder"], "You are Coder. Write code, create files.", env),
            "debugger": XliAgentV2("DEBUGGER", AGENT_IDS["debugger"], "You are Debugger. Find and fix errors.", env),
            "optimizer": XliAgentV2("OPTIMIZER", AGENT_IDS["optimizer"], "You are Optimizer. Improve performance.", env),
        }
        slog.log_structured("INFO", "core", "XliCore initialized")

    async def run_chain(self, task: str, skip_questions: bool = False) -> dict:
        slog.log_structured("INFO", "core", "Starting chain", {"task": task[:100], "skip_questions": skip_questions})
        result = {"task": task, "coder": "", "debugger": "", "optimizer": "", "success": False}

        # Clarification
        final_task = task
        if not skip_questions and len(task.split()) < 20:
            self.env.notify("Clarifying task...", "info")
            try:
                questions = await generate_questions(task, AGENT_IDS["coder"])
                q = Questionnaire(self.env)
                answers = await q.run(questions)

                clarified = task
                for q_obj in questions:
                    if q_obj.id in answers and answers[q_obj.id]:
                        clarified += "\n\n[%s]: %s" % (q_obj.id.upper(), answers[q_obj.id])
                final_task = clarified
                self.env.notify("Task clarified", "info")
                slog.log_structured("INFO", "core", "Task clarified", {"answers": len(answers)})
            except Exception as e:
                slog.log_error("core", "Clarification failed", exc=e)
                self.env.notify("Clarification failed, using original task", "warn")

        # Coder
        self.env.notify("CODER writing code...", "info")
        try:
            result["coder"] = await self.agents["coder"].think(final_task)
            slog.log_structured("INFO", "core", "Coder done", {"output_len": len(result["coder"])})
            self.env.notify("Coder done", "info")
        except Exception as e:
            slog.log_error("core", "Coder failed", exc=e)
            result["coder"] = "ERROR: Coder failed: %s" % e
            self.env.notify("Coder failed: %s" % e, "error")

        # Debugger
        needs_debug = self._has_errors(result["coder"])
        if needs_debug:
            self.env.notify("DEBUGGER checking...", "warn")
            try:
                debug_task = "Check code:\n%s\nIf no errors: 'DONE'" % result["coder"]
                result["debugger"] = await self.agents["debugger"].think(debug_task)
                slog.log_structured("INFO", "core", "Debugger done", {"needs_fix": "NEEDS FIX" in result["debugger"]})

                if "NEEDS FIX" in result["debugger"]:
                    self.env.notify("Fixing errors...", "warn")
                    fix_task = "Fix:\n%s\n\nCode:\n%s" % (result["debugger"][:500], result["coder"][:500])
                    result["coder"] = await self.agents["coder"].think(fix_task)
                    slog.log_structured("INFO", "core", "Fix applied")
                    self.env.notify("Errors fixed", "info")
            except Exception as e:
                slog.log_error("core", "Debugger failed", exc=e)
                self.env.notify("Debugger error: %s" % e, "error")

        # Optimizer
        needs_opt = self._needs_optimize(result["coder"], result["debugger"])
        if needs_opt:
            self.env.notify("OPTIMIZER working...", "info")
            try:
                opt_task = "Optimize:\n%s" % result["coder"]
                result["optimizer"] = await self.agents["optimizer"].think(opt_task)
                slog.log_structured("INFO", "core", "Optimizer done", {"needs_opt": "NEEDS OPTIMIZE" in result["optimizer"]})

                if "NEEDS OPTIMIZE" in result["optimizer"]:
                    self.env.notify("Applying optimization...", "info")
                    apply_task = "Apply:\n%s\n\nCode:\n%s" % (result["optimizer"][:500], result["coder"][:500])
                    result["coder"] = await self.agents["coder"].think(apply_task)
                    slog.log_structured("INFO", "core", "Optimization applied")
                    self.env.notify("Optimized", "info")
            except Exception as e:
                slog.log_error("core", "Optimizer failed", exc=e)
                self.env.notify("Optimizer error: %s" % e, "error")

        result["success"] = True
        result["final"] = result["coder"]
        self.env.notify("TASK COMPLETE", "info")
        slog.log_structured("INFO", "core", "Chain complete", {"success": True, "final_len": len(result["final"])})
        return result

    def _has_errors(self, response: str) -> bool:
        kw = ["error", "exception", "traceback", "bug", "failed", "fail", "needs fix"]
        has = any(k in response.lower() for k in kw)
        slog.log_structured("DEBUG", "core", "Error check: %s" % has)
        return has

    def _needs_optimize(self, coder: str, debugger: str) -> bool:
        kw = ["slow", "performance", "optimize", "refactor", "inefficient"]
        has = any(k in (coder + debugger).lower() for k in kw)
        slog.log_structured("DEBUG", "core", "Optimize check: %s" % has)
        return has


# --- TUI MODE v3 ---

if HAS_TEXTUAL:
    CSS = """
    Screen { background: $surface; }
    .results-grid { grid-size: 3; grid-columns: 1fr 1fr 1fr; grid-rows: auto; height: auto; margin: 1; }
    .result-panel { border: solid $primary; padding: 1; margin: 1; background: $panel; overflow-y: auto; height: auto; }
    .result-panel.coder { border: solid cyan; }
    .result-panel.debugger { border: solid yellow; }
    .result-panel.optimizer { border: solid green; }
    .progress-bar { margin-top: 1; }
    .state-indicator { margin-top: 1; padding: 0 1; }
    .result-content { margin-top: 1; }
    .activity-log { border: solid $accent; height: 18; margin-top: 1; overflow-y: auto; background: $panel; }
    #input-panel { border: solid $primary; margin-top: 1; padding: 1; background: $panel; }
    #run-btn { width: 22; }
    #task-input { width: 1fr; }
    #status-bar { background: $panel; padding: 1; margin-top: 1; }
    """

    class XliTui(App):
        CSS = CSS
        BINDINGS = [("ctrl+c", "quit", "Quit"), ("c", "clear_log", "Clear"),
                    ("f", "focus_input", "Focus"), ("m", "show_mcp", "MCP"),
                    ("q", "skip_questions", "Skip questions")]

        def __init__(self):
            super().__init__()
            self.env = EnvironmentAdapter()
            self.core = XliCore(self.env)
            self.progress_bars = {}
            self.state_widgets = {}
            self.response_widgets = {}
            self.log_widget = None
            self.skip_questions = False

        def compose(self):
            yield Header(show_clock=True)
            with Container():
                with Horizontal():
                    yield Static("FIRE XLI PRO ULTIMATE v3")
                    yield Static("%s" % datetime.now().strftime('%Y-%m-%d'))
                    yield Static("CODER -> DEBUGGER -> OPTIMIZER")
                    yield Static("MCP: %d" % len(get_available_servers()))

                with Grid(classes="results-grid"):
                    for agent_id, title, color in [
                        ("coder", "CODER", "cyan"),
                        ("debugger", "DEBUGGER", "yellow"),
                        ("optimizer", "OPTIMIZER", "green")
                    ]:
                        with Vertical(classes="result-panel %s" % agent_id):
                            yield Static("[bold %s]%s[/bold %s]" % (color, title, color))
                            self.progress_bars[agent_id] = ProgressBar(total=100, show_percentage=False)
                            yield self.progress_bars[agent_id]
                            self.state_widgets[agent_id] = Static("WAITING")
                            yield self.state_widgets[agent_id]
                            self.response_widgets[agent_id] = Static("Waiting...", classes="result-content")
                            yield self.response_widgets[agent_id]

                with Collapsible(title="LIVE LOG", collapsed=False):
                    self.log_widget = ScrollableContainer(classes="activity-log")
                    yield self.log_widget

                with Horizontal(id="input-panel"):
                    self.task_input = Input(placeholder="Enter task...", id="task-input")
                    self.run_button = Button("RUN", variant="primary", id="run-btn")
                    yield self.task_input
                    yield self.run_button

                self.status_bar = Static("Enter — run | q — skip questions | m — MCP", id="status-bar")
                yield self.status_bar

            yield Footer()

        def on_mount(self):
            self.set_focus(self.task_input)
            self._log("XLI PRO v3 started", "SYS")
            self._log("Mode: %s | MCP: %d" % (self.env.name, len(get_available_servers())), "SYS")
            slog.log_structured("INFO", "tui", "TUI mounted")

        def _log(self, msg: str, agent: str = "SYS"):
            if not self.log_widget:
                return
            timestamp = datetime.now().strftime("%H:%M:%S")
            entry = Static("%s [%s] %s" % (timestamp, agent, msg))
            self.log_widget.mount(entry)
            self.log_widget.scroll_end(animate=False)
            slog.log_structured("DEBUG", "tui", msg, {"agent": agent})

        def update_state(self, agent_key: str, state: str, progress: int):
            if agent_key in self.state_widgets:
                self.state_widgets[agent_key].update(state)
            if agent_key in self.progress_bars:
                self.progress_bars[agent_key].progress = progress

        def update_response(self, agent_key: str, response: str):
            if agent_key in self.response_widgets:
                self.response_widgets[agent_key].update(response[:300] if response else "No response")

        def clear_results(self):
            for key in ["coder", "debugger", "optimizer"]:
                self.update_response(key, "Waiting...")
                self.update_state(key, "WAITING", 0)

        async def run_chain(self, task: str):
            self.clear_results()
            self.update_state("coder", "WRITING", 30)
            self._log("TASK: %s" % task[:200], "SYS")
            slog.log_structured("INFO", "tui", "Running chain", {"task": task[:100]})

            try:
                result = await self.core.run_chain(task, skip_questions=self.skip_questions)

                self.update_response("coder", result["coder"][:300])
                self.update_state("coder", "DONE", 100)

                if result["debugger"]:
                    self.update_response("debugger", result["debugger"][:300])
                    self.update_state("debugger", "DONE", 100)
                else:
                    self.update_state("debugger", "SKIPPED", 100)

                if result["optimizer"]:
                    self.update_response("optimizer", result["optimizer"][:300])
                    self.update_state("optimizer", "DONE", 100)
                else:
                    self.update_state("optimizer", "SKIPPED", 100)

                self._log("TASK COMPLETE", "SYS")
                slog.log_structured("INFO", "tui", "Chain complete")
            except Exception as e:
                slog.log_error("tui", "Chain failed", exc=e)
                self._log("ERROR: %s" % e, "SYS")
                self.update_state("coder", "ERROR", 0)

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
                self._log("Log cleared", "SYS")

        def action_focus_input(self):
            self.set_focus(self.task_input)

        def action_show_mcp(self):
            try:
                servers = list_mcp_servers()
                self._log("=== MCP SERVERS ===", "SYS")
                for name, info in servers.items():
                    self._log("%s %s: %s" % ("OK" if info['available'] else "NO", name, info['description'][:40]), "MCP")
            except Exception as e:
                slog.log_error("tui", "MCP list failed", exc=e)
                self._log("MCP error: %s" % e, "SYS")

        def action_skip_questions(self):
            self.skip_questions = not self.skip_questions
            self._log("Questions %s" % ("off" if self.skip_questions else "on"), "SYS")


# --- CLI / HEADLESS v3 ---

async def run_headless(task: str, agent_type: str = "coder",
                       skip_questions: bool = False,
                       output_format: str = "text",
                       notify: bool = False):
    slog.log_structured("INFO", "headless", "Starting", {
        "task": task[:100],
        "agent": agent_type,
        "format": output_format
    })
    env = EnvironmentAdapter()

    if notify:
        env.notify("XLI: %s..." % task[:50], "info")

    core = XliCore(env)
    try:
        result = await core.run_chain(task, skip_questions=skip_questions)
    except Exception as e:
        slog.log_error("headless", "Chain failed", exc=e)
        result = {"task": task, "coder": "ERROR: %s" % e, "debugger": "", "optimizer": "", "success": False, "final": "ERROR: %s" % e}

    if output_format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif output_format == "vim":
        print("XLI_RESULT_START")
        print(result["final"])
        print("XLI_RESULT_END")
    else:
        print("\n" + "=" * 60)
        print("FIRE XLI PRO v3 — Result")
        print("=" * 60)
        print("\nCODER:\n%s" % result["coder"][:500])
        if result["debugger"]:
            print("\nDEBUGGER:\n%s" % result["debugger"][:300])
        if result["optimizer"]:
            print("\nOPTIMIZER:\n%s" % result["optimizer"][:300])
        print("\n" + "=" * 60)
        print("OK Done!")

    if notify:
        status = "OK" if result["success"] else "FAIL"
        env.notify("%s XLI done: %s" % (status, task[:40]),
                  "info" if result["success"] else "error")

    slog.log_structured("INFO", "headless", "Complete", {"success": result["success"]})
    return result


def run_mcp_command(action: str, server_name: str = None):
    slog.log_structured("INFO", "mcp", "Command: %s" % action, {"server": server_name})
    try:
        if action == "list":
            servers = list_mcp_servers()
            print(json.dumps(servers, indent=2, ensure_ascii=False))
        elif action == "info" and server_name:
            servers = get_available_servers()
            if server_name in servers:
                print(json.dumps(servers[server_name], indent=2, ensure_ascii=False))
            else:
                slog.log_structured("ERROR", "mcp", "Server not found", {"name": server_name})
                print("Server '%s' not found" % server_name)
        elif action == "start" and server_name:
            toggle_mcp_server(server_name, True)
            print("MCP '%s' enabled" % server_name)
        elif action == "stop" and server_name:
            toggle_mcp_server(server_name, False)
            print("MCP '%s' disabled" % server_name)
    except Exception as e:
        slog.log_error("mcp", "Command failed: %s" % action, exc=e)
        print("ERROR: %s" % e)


def main():
    parser = argparse.ArgumentParser(description="XLI PRO ULTIMATE v3")
    parser.add_argument("--task", help="Task to execute")
    parser.add_argument("--headless", action="store_true", help="No TUI")
    parser.add_argument("--agent", default="coder", choices=["coder", "debugger", "optimizer"])
    parser.add_argument("--skip-questions", action="store_true", help="Skip clarification")
    parser.add_argument("--output-format", default="text", choices=["text", "json", "vim"])
    parser.add_argument("--notify", action="store_true", help="Neovim notifications")
    parser.add_argument("--mcp-list", action="store_true", help="List MCP servers")
    parser.add_argument("--mcp-start", help="Start MCP server")
    parser.add_argument("--mcp-stop", help="Stop MCP server")
    parser.add_argument("--mcp-info", help="MCP server info")
    parser.add_argument("--debug-file", help="File to debug")
    args = parser.parse_args()

    slog.log_structured("INFO", "main", "XLI started", {"args": str(args)})

    # MCP commands
    if args.mcp_list:
        run_mcp_command("list")
        return
    if args.mcp_start:
        run_mcp_command("start", args.mcp_start)
        return
    if args.mcp_stop:
        run_mcp_command("stop", args.mcp_stop)
        return
    if args.mcp_info:
        run_mcp_command("info", args.mcp_info)
        return

    # Headless / Neovim mode
    if args.headless or args.task or args.debug_file:
        task = args.task or ""
        if args.debug_file:
            task = "debug file: %s" % args.debug_file

        if task:
            asyncio.run(run_headless(
                task=task,
                agent_type=args.agent,
                skip_questions=args.skip_questions,
                output_format=args.output_format,
                notify=args.notify
            ))
            return

    # TUI mode
    if HAS_TEXTUAL:
        console = Console()
        fig = Figlet(font='slant')
        title = fig.renderText("XLI")
        console.print(Panel(Text(title, style="bold cyan"),
                          border_style="bright_cyan",
                          subtitle="[%s]" % datetime.now().strftime('%H:%M:%S')))
        console.print("MCP: %d | Mode: %s\n" % (len(get_available_servers()), EnvironmentAdapter().name))
        XliTui().run()
    else:
        print("Textual not installed. Use --headless --task '...'")
        print("   pip install textual rich pyfiglet")
        slog.log_structured("WARN", "main", "Textual not available, headless only")


if __name__ == "__main__":
    main()
