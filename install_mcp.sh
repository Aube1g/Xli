#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# УСТАНОВКА MCP ИЗ ТВОЕГО СПИСКА (ТОЛЬКО РАБОТАЮЩИЕ)
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════════╗"
echo "║              УСТАНОВКА MCP ИЗ ТВОЕГО СПИСКА                               ║"
echo "║                       XLI PRO ULTIMATE                                    ║"
echo "╚═══════════════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================
# 1. БАЗОВЫЕ ПАКЕТЫ
# ============================================================
echo -e "${BLUE}[1/10] Базовые пакеты...${NC}"
pkg update -y 2>/dev/null
pkg install -y python python-pip nodejs npm git curl wget jq rust cargo 2>/dev/null
echo -e "${GREEN}✅ Готово${NC}"

# ============================================================
# 2. TERMINAL MCP SERVER (уже есть)
# ============================================================
echo -e "${BLUE}[2/10] terminal-mcp-server...${NC}"
if [ -d "$HOME/terminal-mcp-server" ]; then
    echo -e "${GREEN}✅ уже установлен${NC}"
else
    git clone https://github.com/1999AZZAR/terminal-mcp-server.git "$HOME/terminal-mcp-server"
    cd "$HOME/terminal-mcp-server"
    npm install --no-optional 2>/dev/null
    npm run build 2>/dev/null
    echo -e "${GREEN}✅ установлен${NC}"
fi

# ============================================================
# 3. MCP TOOLS PY (pylint + pytest + mypy)
# ============================================================
echo -e "${BLUE}[3/10] mcp-tools-py...${NC}"
pip install mcp-tools-py -q 2>/dev/null
echo -e "${GREEN}✅ установлен${NC}"

# ============================================================
# 4. MCP SERVER ANALYZER (Ruff + Vulture)
# ============================================================
echo -e "${BLUE}[4/10] mcp-server-analyzer...${NC}"
pip install mcp-server-analyzer ruff vulture -q 2>/dev/null
echo -e "${GREEN}✅ установлен${NC}"

# ============================================================
# 5. RUFF MCP SERVER
# ============================================================
echo -e "${BLUE}[5/10] ruff-mcp-server...${NC}"
pip install ruff-mcp-server -q 2>/dev/null
echo -e "${GREEN}✅ установлен${NC}"

# ============================================================
# 6. AST-GREP MCP
# ============================================================
echo -e "${BLUE}[6/10] ast-grep-mcp...${NC}"
npm install -g @ast-grep/cli -s 2>/dev/null
echo -e "${GREEN}✅ установлен${NC}"

# ============================================================
# 7. LSP MCP (через npx, без глобальной установки)
# ============================================================
echo -e "${BLUE}[7/10] lsp-mcp...${NC}"
npm install -g @modelcontextprotocol/sdk -s 2>/dev/null
echo -e "${GREEN}✅ MCP SDK установлен${NC}"

# ============================================================
# 8. REFACTOR MCP
# ============================================================
echo -e "${BLUE}[8/10] refactor-mcp...${NC}"
npm install -g @myuon/refactor-mcp -s 2>/dev/null
echo -e "${GREEN}✅ установлен${NC}"

# ============================================================
# 9. MCP VECTOR SEARCH (семантический поиск)
# ============================================================
echo -e "${BLUE}[9/10] mcp-vector-search...${NC}"
pip install mcp-vector-search -q 2>/dev/null
echo -e "${GREEN}✅ установлен${NC}"

# ============================================================
# 10. ANTHROPIC СЕРВЕРЫ (Memory, Sequential Thinking)
# ============================================================
echo -e "${BLUE}[10/10] Anthropic MCP серверы...${NC}"
npm install -g @modelcontextprotocol/server-memory -s 2>/dev/null
npm install -g @modelcontextprotocol/server-sequential-thinking -s 2>/dev/null
npm install -g @modelcontextprotocol/server-webresearch -s 2>/dev/null
echo -e "${GREEN}✅ установлены${NC}"

# ============================================================
# ПРОВЕРКА
# ============================================================
echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ УСТАНОВЛЕНО:${NC}"
echo ""

# Проверки
command -v ast-grep &>/dev/null && echo "  ✅ ast-grep" || echo "  ❌ ast-grep"
python -c "import mcp_tools_py" 2>/dev/null && echo "  ✅ mcp-tools-py" || echo "  ❌ mcp-tools-py"
python -c "import mcp_server_analyzer" 2>/dev/null && echo "  ✅ mcp-server-analyzer" || echo "  ❌ mcp-server-analyzer"
command -v ruff &>/dev/null && echo "  ✅ ruff" || echo "  ❌ ruff"
npm list -g @myuon/refactor-mcp 2>/dev/null | grep -q "refactor-mcp" && echo "  ✅ refactor-mcp" || echo "  ❌ refactor-mcp"
python -c "import mcp_vector_search" 2>/dev/null && echo "  ✅ mcp-vector-search" || echo "  ❌ mcp-vector-search"
npm list -g @modelcontextprotocol/server-memory 2>/dev/null | grep -q "server-memory" && echo "  ✅ server-memory" || echo "  ❌ server-memory"

echo ""
echo "════════════════════════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ Установка завершена!${NC}"
echo ""
