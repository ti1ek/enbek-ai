# EVALS.md — Оценка качества Enbek AI

## Методология

### Golden Dataset

**40 примеров** в `data/golden/qa.jsonl`:

| Категория | Вопросов |
|---|---|
| Отпуска | 4 |
| Увольнение | 6 |
| Оплата труда | 7 |
| Трудовой договор | 5 |
| Рабочее время | 5 |
| Охрана труда | 1 |
| Out-of-scope | 1 |
| Edge cases | 3 |
| **Multi-hop (q033-q040)** | **8** |

Каждый пример: `question`, `expected_articles`, `expected_answer_keywords`, `category`, `source`.
Multi-hop кейсы дополнительно содержат `multi_hop: true`, `expected_chain` (упорядоченный массив
`{doc_type, article_or_point, must_appear_in_context, must_appear_in_answer}`) и опционально
`expected_conclusion` — финальный вывод, который должен дать ответ.

---

## Метрики

| Метрика | Описание |
|---|---|
| **hit@5** | Ожидаемая статья ТК найдена в top-5 retrieved chunks |
| **keyword_match** | Доля ожидаемых ключевых слов в ответе |
| **chain_match** *(multi-hop)* | Доля элементов `expected_chain`, найденных в sources/answer **в правильном порядке** |
| **wrong_conclusion_rate** *(multi-hop)* | LLM-судья: 1 — итоговый вывод противоречит цепочке или упускает ключевую норму; 0 — корректен |
| **faithfulness** | LLM-судья (gpt-4.1-mini): нет утверждений без опоры на контекст (0-1) |
| **relevance** | LLM-судья: релевантность ответа вопросу (1-5 → 0-1) |
| **latency_ms** | Полное время ответа |
| **cost_usd** | Стоимость LLM-вызовов |

---

## A/B Результаты: Advanced vs Basic RAG

Прогон: 32 примера (advanced: 31 — один 429 TPM error на q026), 2026-05-20. Корпус: 26 237 точек в Qdrant.

| Метрика | Basic RAG | Advanced RAG | Δ |
|---|---|---|---|
| **hit@5** | **0.500** | 0.355 | -0.145 |
| **keyword_match** | 0.560 | **0.637** | +0.077 |
| **faithfulness** | **0.733** | 0.700 | -0.033 |
| **relevance** | 0.867 | **0.883** | +0.016 |
| **avg_latency_ms** | **7 378** | 17 857 | +10 479 |
| **cost_usd (32 запроса)** | **$0.41** | — | — |

---

## Анализ результатов

**Гипотеза:** Advanced RAG даст +20%+ к hit@5 за счёт HyDE и Cohere rerank. **Результат: опровергнута.**

Basic выиграл по hit@5 (0.500 > 0.355). Три причины:

1. **HyDE размывает юридический запрос.** Усреднение вектора оригинального вопроса и гипотетического ответа LLM смещает поиск в семантическое пространство «ответа», а не «нормативного текста». Для точных правовых формулировок это даёт регрессию: модель ищет текст, похожий на её же ответ, а не на статью ТК.

2. **Reranker теряет на расширенном корпусе.** Basic берёт top-5 напрямую; Advanced берёт top-15, затем Cohere переупорядочивает. В корпусе 26K чанков (включая 14K исторических) 15 кандидатов оказываются разнородными — reranker переоценивает семантически близкие исторические версии норм вместо действующей.

3. **Keyword_match и relevance выше у Advanced** (0.637 > 0.560; 0.883 > 0.867): Advanced генерирует более детальные и структурированные ответы. Проблема именно в retrieval, не в синтезе.

**Вывод для production:**
- **Basic retrieval** как основной путь — быстрее (7.4s vs 17.9s) и точнее по hit@5
- **Advanced синтез** (GPT-4.1 с полным контекстом) — оставляем, он даёт лучшие ответы
- **HyDE** — отключить или применять только при hit@5=0 (fallback)
- **Исторические чанки** — фильтровать `in_force=True` строже на стадии retrieval

---

## Hyperparameter Sweep

| Параметр | Значения | Выбор | Обоснование |
|---|---|---|---|
| temperature синтезатора | 0.0 / 0.1 / 0.3 | **0.1** | 0.0 — слишком формально, 0.3 — галлюцинации на edge cases |
| top_k retrieve | 5 / 10 / 15 | **15** (advanced) / **5** (basic) | Больший пул для Cohere reranker |
| parent_text cap | 2000 / 4000 / 8000 | **4000** | 4000 = 1-2 статьи полностью; 8000 перегружает prompt |
| rerank top_n | 3 / 5 / 7 | **5** | 7 добавляет шум, 3 теряет покрытие |

---

## Известные ограничения

| Ограничение | Причина |
|---|---|
| hit@5 < 0.6 | Строгий matching article_id; частичные совпадения не учитываются |
| Latency Advanced ~29s | HyDE: 2 embedding + GPT-4.1-mini + Cohere; в prod → кешировать embeddings |
| КоАП — 23 статьи (whitelist) | Намеренно; полный КоАП — off-topic content |
| Cost tracking в graph path | `cost_usd=0.0` в LangGraph — трейсы в LangSmith содержат реальные токены |
| LLM judge: мало примеров | 10 вызовов лимит; для production — 100+ примеров с полным judging |

---

## Запуск эвалюаций

```bash
# Advanced pipeline
uv run python scripts/run_evals.py --pipeline advanced

# A/B сравнение
uv run python scripts/run_evals.py --pipeline both

# Только multi-hop кейсы (q033-q040)
uv run python scripts/run_evals.py --pipeline advanced --multi-hop --tag baseline_multihop

# Результаты
cat data/evals/*_summary.json
```

---

## SOTA flags (Self-RAG, decomposition, citation graph)

Граф `apps/api/graph.py` поддерживает четыре env-флага (по умолчанию все `false` — поведение
идентично базовому advanced):

| Флаг | Что делает |
|---|---|
| `ENABLE_VERIFIER` | После `synthesizer` добавляет `verifier_node` (Self-RAG критика). При обнаружении непокрытой подзаконки делает один-два повторных retrieval-pass'а с целевым запросом. Лимит итераций — 2. |
| `ENABLE_DECOMPOSE` | В `retriever_node` декомпозирует сложный вопрос на 1-4 сущностных под-вопроса и добавляет hop1 search по каждому. |
| `ENABLE_GRAPH_EXPAND` | Использует side-car `data/chunks/citation_edges.json` (6126 рёбер). После hop1+hop2 для каждого retrieved chunk дотягивает 1-3 целевых чанка по citation edges («пункт 7 настоящих Правил» → block_4 V1500012533). |
| `ENABLE_STRICT_CITATION_GUARD` | Расширяет `citation_guard_node`: проверяет, что цитируемые в ответе пункты (`п.N`) присутствуют в контексте. |
| `ENABLE_HYBRID` | Заменяет dense_search hop1 на hybrid (RRF dense+sparse). Требует populated sparse vectors в коллекции — сейчас не populated, флаг безопасно остаётся off. |

### Build citation graph (one-time)

```bash
# Сканирует все чанки Qdrant, извлекает citation edges → data/chunks/citation_edges.json
.venv/bin/python -m packages.rag.ingestion.build_citation_graph
```

Pure side-car, Qdrant не модифицируется. Откат = удалить файл.

### Multi-hop baseline (advanced, без флагов)

8 кейсов q033-q040, 2026-05-21:

| Метрика | Значение |
|---|---|
| chain_match | 0.458 |
| wrong_conclusion_rate | 0.125 |
| hit@5 | 0.625 |
| keyword_match | 0.606 |
| faithfulness | 0.500 |
| relevance | 0.844 |
| avg_latency_ms | 21 542 |

Эталонный q033 (5 кал. дней → 3 раб.) проваливается с `chain_match=0.0, wrong_conclusion=1`
из-за того, что содержательные пункты ПП РК 1406 (п.7, п.15) разнесены по `ministerial_order`
V1500012533, а не доступны напрямую как `government_decree P1200001406`. P1200001406 в Qdrant
есть, но содержит только 3 заголовочных чанка без нормативного содержания.

### Эксперимент: ENABLE_GRAPH_EXPAND + cross-doc edges (2026-05-23)

Построено 519 cross-doc edges (`data/chunks/cross_doc_edges.json`): ст.96 ТК → V1500012533
block_4/5/6/7 (правила расчёта рабочих дней). Флаг `ENABLE_GRAPH_EXPAND=true`:

| Метрика | baseline | cross_doc_graph | Δ |
|---|---|---|---|
| chain_match | 0.458 | 0.438 | **-0.020** |
| hit@5 | 0.625 | 0.250 | **-0.375** |
| wrong_conclusion_rate | 0.125 | 0.125 | 0 |

**Причина регрессии hit@5:** граф добавляет cross-doc чанки для КАЖДОЙ ТК-статьи из hop1 (prepend),
они занимают слоты и вытесняют нужные статьи ТК. Для q033: ст.95 извлечена → 5 edges к V1500012533
prepended → ст.96 не попала в финальные sources.

**Вывод:** `ENABLE_GRAPH_EXPAND` вреден в текущей реализации. Флаг остаётся `false` (default).
Cross-doc edges корректно построены, но требуют таргетированного применения (например, только
при verifier-retry, не превентивно для всех чанков).
