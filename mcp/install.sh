#!/usr/bin/env bash
set -e

echo "=== enbek MCP — установка ==="

# 1. Ollama
if command -v ollama &>/dev/null; then
  echo "✓ Ollama уже установлена"
else
  echo "→ Устанавливаю Ollama..."
  if [[ "$OSTYPE" == "darwin"* ]]; then
    if command -v brew &>/dev/null; then
      brew install ollama
    else
      echo "  Homebrew не найден. Скачай Ollama вручную: https://ollama.ai"
      exit 1
    fi
  else
    curl -fsSL https://ollama.ai/install.sh | sh
  fi
  echo "✓ Ollama установлена"
fi

# 2. Модель для маскировки ПДн
if ollama list 2>/dev/null | grep -q "llama3.2:3b"; then
  echo "✓ Модель llama3.2:3b уже скачана"
else
  echo "→ Скачиваю модель llama3.2:3b (~2 GB)..."
  ollama pull llama3.2:3b
  echo "✓ Модель готова"
fi

# 3. Python зависимости
echo "→ Устанавливаю Python зависимости..."
pip install -r "$(dirname "$0")/requirements.txt" -q
echo "✓ Зависимости установлены"

# 4. .env файл
ENV_FILE="$(dirname "$0")/.env"
if [ -f "$ENV_FILE" ]; then
  echo "✓ .env уже существует"
else
  cp "$(dirname "$0")/.env.example" "$ENV_FILE"
  echo ""
  echo "⚠️  Открой файл mcp/.env и вставь свой OpenAI API ключ:"
  echo "    OPENAI_API_KEY=sk-..."
fi

echo ""
echo "=== Готово! ==="
echo ""
echo "Следующий шаг — добавь в Claude Desktop (Settings → Developer → Edit Config):"
echo ""
echo '{'
echo '  "mcpServers": {'
echo '    "enbek": {'
echo '      "command": "python",'
echo "      \"args\": [\"$(pwd)/server.py\"],"
echo '      "env": {'
echo '        "OPENAI_API_KEY": "sk-твой-ключ"'
echo '      }'
echo '    }'
echo '  }'
echo '}'
