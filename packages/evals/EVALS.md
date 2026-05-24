# EVALS.md — Оценка качества Enbek AI

## Методология

### Golden Dataset

**25 примеров** в `data/golden/np_golden.jsonl` — вопросы по НП ВС РК №1/2024 (нормативное постановление Верховного суда о трудовых спорах).

Каждый пример: `question`, `expected_articles`, `expected_answer_keywords`, `category`, `source`.

---

## Метрики

| Метрика | Описание |
|---|---|
| **faithfulness** | LLM-судья (gpt-4.1-mini): нет утверждений без опоры на контекст (0–1) |
| **answer_relevancy** | LLM-судья: релевантность ответа вопросу (0–1) |
| **context_precision** | Доля релевантных чанков среди retrieved (0–1) |
| **context_recall** | Покрытие ожидаемых фактов retrieved контекстом (0–1) |
| **answer_correctness** | Совпадение ответа с эталоном (0–1) |
| **latency_ms** | Полное время ответа |

Оценка через RAGAS 0.2.6, judge-модель: `gpt-4.1-mini`.

---

## RAGAS A/B/C: Basic vs Advanced vs Graph (НП ВС РК, n=25)

Прогон: 2026-05-24. Golden set: `data/golden/np_golden.jsonl` (25 вопросов по НП ВС РК №1/2024).
RAGAS judge: gpt-4.1-mini.

| Метрика | Basic | Advanced | Graph |
|---|---|---|---|
| **faithfulness** | **0.714** | 0.661 | 0.698 |
| **answer_relevancy** | **0.927** | 0.764 | 0.690 |
| **context_precision** | 0.589 | **0.777** | 0.685 |
| **context_recall** | **0.640** | 0.460 | 0.420 |
| **answer_correctness** | **0.446** | 0.436 | 0.414 |
| **avg_latency_ms** | **6 977** | 17 892 | 17 751 |

**Выводы:**
- Basic выигрывает по faithfulness, answer_relevancy, context_recall и скорости (2.6x быстрее)
- Advanced лидирует только по context_precision (0.777) — лучше отбирает релевантные чанки
- Graph (ENABLE_GRAPH_EXPAND) не даёт прироста на НП-вопросах

---

## Ablation Study: Advanced RAG — отключение фич

Прогон: 2026-05-24. Метрика: faithfulness (RAGAS, gpt-4.1-mini). n=25, НП golden set.

| Конфигурация | Faithfulness | Δ vs Advanced | Вывод |
|---|---|---|---|
| **Advanced (baseline)** | **0.661** | — | все фичи включены |
| no_rerank | 0.657 | -0.004 | Rerank почти не влияет |
| no_hyde | 0.647 | -0.014 | HyDE незначительно помогает |
| no_rerank + no_verifier | 0.680 | **+0.019** | без этих двух чуть лучше |
| no_verifier | 0.596 | -0.065 | Verifier важен |
| no_hybrid | 0.583 | -0.078 | Hybrid search критичен |
| **no_hyde + no_rerank** | **0.703** | **+0.042** | лучший результат |
| no_hyde + no_hybrid | 0.559 | -0.102 | худший |

**Ключевые инсайты:**

1. **Hybrid search — самая важная фича** (-0.078 без него). BM25 + dense покрывают юридические термины которые семантический поиск упускает.

2. **Verifier второй по важности** (-0.065). Без него модель чаще включает непроверенные утверждения.

3. **HyDE + Rerank вместе создают шум** (+0.042 без обоих). HyDE смещает вектор в пространство «ответа», reranker переупорядочивает уже смещённые кандидаты.

4. **Оптимальная конфигурация: Advanced без HyDE и без Rerank** — faithfulness 0.703, быстрее на ~4с.

---

## Hyperparameter Sweep

| Параметр | Значения | Выбор | Обоснование |
|---|---|---|---|
| temperature синтезатора | 0.0 / 0.1 / 0.3 | **0.1** | 0.0 — слишком формально, 0.3 — галлюцинации на edge cases |
| top_k retrieve | 5 / 10 / 15 | **15** (advanced) / **5** (basic) | Больший пул для Cohere reranker |
| parent_text cap | 2000 / 4000 / 8000 | **4000** | 4000 = 1–2 статьи полностью; 8000 перегружает prompt |
| rerank top_n | 3 / 5 / 7 | **5** | 7 добавляет шум, 3 теряет покрытие |

---

## Итоговая рекомендация для Production

| Критерий | Рекомендация |
|---|---|
| **Пайплайн** | Advanced RAG с `ENABLE_HYDE=false ENABLE_RERANK=false` |
| **Обоснование** | Faithfulness 0.703 (лучший из всех), hybrid+verifier сохранены |
| **Latency** | ~13–14s (vs 17.9s baseline advanced, vs 7.0s basic) |
| **vs Basic** | Basic быстрее, но хуже по context_precision (0.589 vs 0.777) |
| **Graph expand** | Отключён — регрессия подтверждена по faithfulness и context_recall |

```bash
# Production запуск
ENABLE_HYDE=false ENABLE_RERANK=false uv run python apps/api/main.py
```

---

## Запуск эвалюаций

```bash
# A/B/C: Basic vs Advanced vs Graph
uv run python scripts/run_ragas_evals.py --pipeline basic
uv run python scripts/run_ragas_evals.py --pipeline advanced
uv run python scripts/run_ragas_evals.py --pipeline graph

# Ablation: отключение фич
uv run python scripts/run_ragas_evals.py --pipeline advanced --no-hyde --no-rerank

# Результаты
cat data/evals/ragas_final_*.json
```
