# SKILL: Enbek — Kazakhstan Labour Law Search

## Overview

This skill enables Claude to answer questions about Kazakhstan labour legislation by querying the Enbek AI knowledge base via MCP tools. It activates when a user asks about labour law, employment rights, or HR compliance in Kazakhstan (ТК РК).

---

## Trigger Conditions

The skill fires when the user's message matches **any** of the following patterns:

| Pattern | Example |
|---|---|
| Explicit labour law question | «Какой срок уведомления при увольнении по инициативе работодателя?» |
| Article reference in ТК РК | «Что говорит статья 52 ТК РК?» |
| HR compliance query | «Можно ли уволить беременную сотрудницу?» |
| Kazakhstan labour dispute | «Порядок обращения в согласительную комиссию» |
| Payroll / benefits question | «Как рассчитывается компенсация при увольнении?» |
| Keyword match | трудовой договор, ТК РК, увольнение, оклад, отпуск, охрана труда |

The skill does **not** fire for:
- General questions unrelated to Kazakhstan law
- Questions about legislation of other countries (unless comparative)
- Programming, math, or non-legal topics

---

## Skill Description

When triggered, Claude:

1. **Masks PII** — calls `search_labor_code(query)` which internally runs `mask_pii()` via local Ollama (`llama3.2:3b`) before any network call. Personal data (ФИО, ИИН, address) never leaves the local machine.

2. **Retrieves relevant norms** — the masked query is sent to Qdrant Cloud (`kz_legal` collection). Hybrid dense+sparse retrieval returns ranked chunks from:
   - Трудовой кодекс РК (ТК РК)
   - Социальный кодекс
   - КоАП (ст. 86–99, 414–420)
   - НП ВС РК №1/2024 (Верховный Суд)
   - Приказы и разъяснения Минтруда РК

3. **Synthesizes answer** — Claude formulates a response grounded strictly in the retrieved sources, with clickable citations to official adilet.zan.kz pages.

---

## Tools Used

| Tool | Purpose |
|---|---|
| `search_labor_code(query: str)` | Combined PII masking + knowledge base retrieval |
| `mask_pii(text: str)` | Standalone PII masking via Ollama |
| `retrieve(query: str)` | Direct Qdrant search (no masking) |

All tools are provided by the `mcp/tools.py` MCP server.

---

## MCP Server Setup

The skill requires the Enbek MCP server to be running. See [./mcp/README.md](./mcp/README.md) for full installation instructions.

Quick setup for Claude Code:
```json
// .claude/mcp.json
{
  "mcpServers": {
    "enbek": {
      "command": "uv",
      "args": ["run", "python", "-m", "mcp", "mcp/tools.py"],
      "cwd": "/path/to/enbek-ai"
    }
  }
}
```

Prerequisites: Ollama running locally with `llama3.2:3b`, valid `QDRANT_URL` and `QDRANT_API_KEY` in `.env`.

---

## Response Format

Claude MUST follow these constraints when this skill is active:

- Cite the **specific article** (`ст. 52 ТК РК`) with a clickable link when available
- Do **not** invent legal norms not present in retrieved sources
- If retrieved context is insufficient, say so explicitly and suggest consulting a lawyer
- Distinguish between **действующая редакция** and historical versions
- Apply source hierarchy: Кодекс > ПП > Приказ > НП ВС > Минтруд Q&A

---

## Example Interaction

**User:** Меня зовут Алия Сейткали, ИИН 880101400123. Могут ли меня уволить, пока я нахожусь на больничном?

**Skill execution:**
1. `mask_pii()` → «Меня зовут [ИМЯ], ИИН [ИИН]. Могут ли меня уволить, пока я нахожусь на больничном?»
2. `retrieve()` → статьи 54, 55 ТК РК + разъяснение Минтруда
3. Claude answers with citations, user's PII never sent to cloud

**Response:** «Нет. Согласно [ст. 54 ТК РК](https://adilet.zan.kz/...), расторжение трудового договора по инициативе работодателя не допускается в период временной нетрудоспособности работника...»

---

## Why This Skill Instead of a Prompt

A prompt can instruct Claude _how_ to answer, but cannot give it access to 34+ legal documents and their current redactions. This skill adds:

- **Up-to-date legal knowledge** without fine-tuning (knowledge base updated via `scripts/check_updates.py`)
- **Local PII protection** — no personal data in cloud API calls
- **Grounded citations** — answers link to official government sources
- **Source hierarchy enforcement** — conflict resolution between legal acts

---

## Skill File Location

```
.claude/commands/labor-law.md   ← Claude Code slash command
SKILL.md                        ← this documentation file
mcp/tools.py                    ← MCP server implementation
mcp/README.md                   ← installation guide
```
