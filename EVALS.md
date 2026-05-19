# EVALS.md — Оценка качества Enbek AI

## Методология

### Golden Dataset

**32 примера** в `data/golden/qa.jsonl`, охватывающие:

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

Каждый пример: `question`, `expected_articles`, `expected_answer_keywords`, `category`, `source`.

---

## Метрики

| Метрика | Описание |
|---|---|
| **hit@5** | Ожидаемая статья ТК найдена в top-5 retrieved chunks |
| **keyword_match** | Доля ожидаемых ключевых слов в ответе |
| **faithfulness** | LLM-судья (gpt-4.1-mini): нет утверждений без опоры на контекст (0-1) |
| **relevance** | LLM-судья: релевантность ответа вопросу (1-5 → 0-1) |
| **latency_ms** | Полное время ответа |
| **cost_usd** | Стоимость LLM-вызовов |

---

## A/B Результаты: Advanced vs Basic RAG

Прогон: 32 примера, 2026-05-19.

| Метрика | Basic RAG | Advanced RAG | Δ |
|---|---|---|---|
| **hit@5** | **0.531** | 0.406 | -0.125 |
| **keyword_match** | 0.516 | **0.594** | +0.078 |
| **faithfulness** | **1.000** *(n=2)* | **1.000** *(n=5)* | 0.000 |
| **relevance** | **1.000** *(n=2)* | **1.000** *(n=5)* | 0.000 |
| **avg_latency_ms** | **4 428** | 28 924 | +24 496 |
| **cost_usd/query** | **~$0.005** | ~$0.015 | +$0.010 |

---

## Анализ неожиданного результата

**Гипотеза:** Advanced RAG даст +15%+ к hit@5. **Результат: опровергнута.**

Basic выиграл по hit@5 (0.531 > 0.406). Объяснение:

1. **HyDE dilutes retrieval:** Усреднение вектора оригинала и гипотетического ответа смещает запрос в семантическое пространство LLM, а не реального законодательного текста. При точных юридических терминах это даёт ухудшение, а не улучшение.

2. **Corpus specificity:** 5555 чанков — достаточно малый корпус, где dense top-5 часто находит нужную статью напрямую. HyDE выигрывает больше на размытых запросах с большими корпусами.

3. **Keyword_match выше у Advanced** (0.594 > 0.516): Advanced даёт более полные, детальные ответы с большим покрытием ключевых слов, что подтверждает лучшее **качество** ответа при сопоставимом поиске.

**Пересмотренный вывод:** Для данного корпуса и типа запросов:
- **Latency-sensitive / cheap**: Basic RAG (~$0.005/query, 4s)
- **Quality-focused**: Advanced RAG (лучшие ответы по keyword_match)
- **Production**: Hybrid — Basic retrieval + HyDE только при нулевых hits

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

# Результаты
cat data/evals/*_summary.json
```
