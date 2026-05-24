#!/usr/bin/env bash
# Enbek AI MCP — автоматическая установка
# Запуск: ./apps/mcp_server/setup.sh

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔═══════════════════════════════════════╗"
echo "║        Enbek AI MCP — Установка       ║"
echo "║  Трудовое право РК + Защита ПДн       ║"
echo "╚═══════════════════════════════════════╝"
echo -e "${NC}"

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$REPO_DIR/.env"
CLAUDE_CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

# ── 1. Проверка зависимостей ──────────────────────────────────────────────────
echo -e "${BLUE}[1/4] Проверка зависимостей...${NC}"

if ! command -v uv &>/dev/null; then
    echo -e "${YELLOW}uv не найден. Устанавливаю...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo -e "${GREEN}✓ uv $(uv --version)${NC}"

cd "$REPO_DIR"
uv sync --quiet
echo -e "${GREEN}✓ Python зависимости установлены${NC}"

# ── 2. API ключи ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[2/4] Настройка API ключей...${NC}"

# Читаем существующие значения если есть
existing_openai=""
if [ -f "$ENV_FILE" ]; then
    existing_openai=$(grep "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"')
fi

# OpenAI — единственное что вводит пользователь
if [ -n "$existing_openai" ]; then
    echo -e "${GREEN}✓ OpenAI API ключ уже настроен${NC}"
    OPENAI_KEY="$existing_openai"
else
    echo -e "${YELLOW}Введите ваш OpenAI API ключ (sk-...):${NC}"
    read -r -s OPENAI_KEY
    if [ -z "$OPENAI_KEY" ]; then
        echo -e "${RED}Ошибка: OpenAI API ключ обязателен${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ OpenAI ключ принят${NC}"
fi

# Qdrant и остальные параметры — берутся из .env.default который идёт с репо
if [ -f "$REPO_DIR/.env.default" ]; then
    cp "$REPO_DIR/.env.default" "$ENV_FILE"
fi

# Записываем/обновляем только OpenAI ключ
if grep -q "^OPENAI_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    sed -i '' "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$OPENAI_KEY|" "$ENV_FILE"
else
    echo "OPENAI_API_KEY=$OPENAI_KEY" >> "$ENV_FILE"
fi
echo -e "${GREEN}✓ .env сохранён${NC}"

# ── 3. Claude Desktop конфиг ──────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[3/4] Настройка Claude Desktop...${NC}"

mkdir -p "$(dirname "$CLAUDE_CONFIG")"

NEW_SERVER=$(cat <<EOF
{
  "command": "uv",
  "args": ["run", "python", "apps/mcp_server/server.py"],
  "cwd": "$REPO_DIR"
}
EOF
)

if [ -f "$CLAUDE_CONFIG" ]; then
    # Добавляем enbek-ai в существующий конфиг через Python
    python3 - <<PYEOF
import json, sys

config_path = "$CLAUDE_CONFIG"
with open(config_path) as f:
    config = json.load(f)

config.setdefault("mcpServers", {})["enbek-ai"] = {
    "command": "uv",
    "args": ["run", "python", "apps/mcp_server/server.py"],
    "cwd": "$REPO_DIR"
}

with open(config_path, "w") as f:
    json.dump(config, f, indent=2, ensure_ascii=False)

print("✓ enbek-ai добавлен в Claude Desktop конфиг")
PYEOF
else
    cat > "$CLAUDE_CONFIG" <<EOF
{
  "mcpServers": {
    "enbek-ai": $NEW_SERVER
  }
}
EOF
    echo -e "${GREEN}✓ Claude Desktop конфиг создан${NC}"
fi

# ── 4. Проверка ───────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[4/4] Проверка MCP сервера...${NC}"
uv run python -c "
import sys; sys.path.insert(0, '.')
from apps.mcp_server.server import mcp
tools = mcp._tool_manager.list_tools()
print(f'✓ MCP сервер запускается, инструментов: {len(tools)}')
for t in tools: print(f'   • {t.name}')
"

echo ""
echo -e "${GREEN}╔═══════════════════════════════════════╗"
echo "║           Установка завершена!         ║"
echo "╚═══════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${YELLOW}Следующий шаг:${NC} перезапустите Claude Desktop"
echo -e "  Иконка 🔨 в чате означает что MCP подключён"
echo ""
echo -e "  ${YELLOW}Пример вопроса:${NC}"
echo -e '  "Законно ли увольнение по ст.52 ТК РК если сотрудник'
echo -e '   не подписал уведомление? Вот приказ: [текст документа]"'
echo ""
