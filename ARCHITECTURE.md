# Enbek AI — Архитектура системы

## Обзор

AI-платформа для консультаций по трудовому праву РК. Решает три задачи:
1. **Q&A** — ответы на вопросы по ТК РК со ссылками на статьи
2. **Doc Check/Fix** — проверка и улучшение трудовых документов
3. **Doc Generate** — генерация договоров по параметрам

---

## Граф агентов (LangGraph)

```
                        ┌─────────────┐
     Вопрос ───────────►│  Classifier  │
                        └──────┬──────┘
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
         "qa"           "doc_*"          "out_of_scope"
              │                │                 │
    [pipeline=advanced]  [Doc Processor]  "Вне области"
              │
    ┌─────────▼──────────┐
    │  Rephraser/HyDE    │  gpt-4.1-mini
    │  canonical + hyde  │  ~200ms
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │  Retriever         │  text-embedding-3-small
    │  Qdrant hybrid     │  dense + sparse (RRF)
    │  top-15 chunks     │  ~300ms
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │  Reranker          │  Cohere Rerank 3.5
    │  top-15 → top-5    │  ~100ms
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │  Synthesizer       │  gpt-4.1
    │  answer + sources  │  ~3000ms
    └─────────┬──────────┘
              │
    ┌─────────▼──────────┐
    │  Citation Guard    │  regex check
    │  ст.N ∈ context?   │  ~5ms
    └─────────┬──────────┘
              │ fail (≤3 iter)
              └──────────────► Synthesizer (retry)
```

---

## RAG Pipeline

### Advanced RAG (production)

1. **Query Rephrasing** — `gpt-4.1-mini` возвращает:
   - `canonical` — юридически точная формулировка
   - `hyde` — гипотетический ответ для embedding (HyDE)
   - `synonyms` — 2-3 альтернативные формулировки

2. **Dual Embedding** — усреднение векторов оригинала и HyDE

3. **Hybrid Retrieval** — Qdrant `prefetch` + RRF fusion:
   - Dense: cosine similarity, `text-embedding-3-small`
   - Sparse: IDF-weighted BM25

4. **Cohere Rerank 3.5** — top-15 → top-5, русскоязычный домен

5. **Synthesizer GPT-4.1** — использует `parent_text` (контекст всей статьи) для генерации

6. **Citation Guard** — проверяет что `ст.N` из ответа есть в контексте; при провале — повтор (max 3)

### Basic RAG (baseline для A/B)

Query → embed → dense top-5 → GPT-4.1 → ответ

---

## Источники данных

### Иерархия (hierarchy_weight)

```
1.0  Трудовой кодекс РК             (K1500000414, 221 статья)
0.95 Социальный кодекс РК           (K2300000224, 272 статьи)
0.90 КоАП РК (трудовые статьи)      (K1400000235, 23 статьи)
0.85 НП ВС РК о трудовых спорах     (P170000009S)
0.80 ПП РК (ср. зарплата)           (P1200001406)
0.60 Q&A Минтруда dialog.egov.kz    (337 пар)
```

### Структура чанка (Qdrant payload)

```json
{
  "chunk_id": "K1500000414_54_2",
  "text": "Параграф (для embedding)",
  "parent_text": "Статья 54. Гарантии... (для LLM контекста, до 4000 символов)",
  "source_type": "labor_code",
  "doc_id": "K1500000414",
  "article": "54",
  "paragraph": "2",
  "in_force": true,
  "hierarchy_weight": 1.0,
  "url": "https://adilet.zan.kz/rus/docs/K1500000414#z54"
}
```

### Парсинг adilet.zan.kz

Сайт использует плоский HTML без вложенных div-контейнеров статей.
Статьи идентифицируются по паттерну `<a name="zN"></a>Статья M.` — regex-сплит по всему документу.
Результат: корректные номера статей (ст.1-250 для ТК РК).

---

## Ключевые технические решения

### Почему Qdrant, а не Chroma/Pinecone?
- Нативный гибридный поиск (`prefetch` + RRF) без дополнительных библиотек
- Payload filtering: `in_force=true`, `source_type IN (...)`, иерархический boost
- 1GB бесплатный tier, production-ready

### Почему GPT-4.1, а не Claude?
- OpenAI Free Tier (data-sharing): 1M токенов GPT-4.1/день бесплатно
- Лучшее качество на юридическом русском среди тестируемых моделей
- Единый API-ключ для embeddings + LLM

### Почему Cohere Rerank, а не cross-encoder локально?
- Trial: 1000 req/мес бесплатно — покрывает MVP и demo
- Лучший benchmark на русском юридическом домене
- 100ms latency vs 500ms+ для локальной модели

### Почему LangGraph, а не LangChain/CrewAI?
- Явный граф с TypedDict State — читаем и отлаживаем
- Нативные условные рёбра (branching) и циклы (citation guard loop)
- Нативная интеграция с LangSmith

### Почему parent-child chunking?
- Embeddим параграф (точный поиск), LLM получает всю статью (полный контекст)
- Решает проблему "needle in haystack" без потери точности retrieval

---

## MCP-сервер (Privacy Layer)

Локальный процесс между пользователем и облачными LLM.

```
Документ с ПДн
      │
  [mask_pii]        regex: ИИН (+ checksum), ФИО, тел, email, IBAN
      │              возвращает masked_text + mapping для восстановления
  Masked doc ──────► Cloud LLM (GPT-4.1)
      │
  Ответ пользователю
```

**Tools:**
1. `mask_pii` — маскировка ПДн, возвращает `masked_text`, `mapping`, `stats`
2. `validate_kz_iin` — валидация ИИН (алгоритм Минюста РК), извлечение даты рождения и пола

---

## Skill: kz-legal-citation-formatter

Встроен в системный промпт синтезатора. Обеспечивает единый стандарт цитирования:
- `ст. 52 п. 1 пп. 2) ТК РК` (не "ст.52 ТК" и не "статья 52")
- URL на adilet.zan.kz для каждой нормы
- Дисклеймер "не является юридической консультацией"

Вынесен в отдельный SKILL.md для переиспользования без дублирования системного промпта.

---

## Деплой

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  Vercel     │────►│  Fly.io      │────►│  Qdrant Cloud│
│  Next.js 15 │     │  FastAPI     │     │  kz_legal    │
│  (после MVP)│     │  LangGraph   │     │  5555 points │
└─────────────┘     └──────┬───────┘     └──────────────┘
                           │
                    ┌──────▼───────┐
                    │  Supabase    │
                    │  Auth + DB   │
                    └──────────────┘
```
