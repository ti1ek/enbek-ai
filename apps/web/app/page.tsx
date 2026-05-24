"use client";

import { useState } from "react";
import AskBox from "@/components/AskBox";
import AnswerCard from "@/components/AnswerCard";
import TypingIndicator from "@/components/TypingIndicator";
import McpBanner from "@/components/McpBanner";
import { ask, extractFile, type AskResponse, type Turn } from "@/lib/api";

const GITHUB_URL = "https://github.com/ti1ek/enbek-ai";

// Лучший по эвалу пайплайн — используется всегда.
const PIPELINE = "advanced" as const;

const DEFAULT_DOC_QUESTION =
  "Проанализируй приложенный документ на соответствие трудовому праву РК.";

interface ChatTurn {
  question: string; // что показываем пользователю как его реплику
  answer: AskResponse | null; // null, пока идёт ответ
  error: string | null;
}

export default function Home() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [loading, setLoading] = useState(false);

  const hasConversation = turns.length > 0;

  // История для бэкенда — только завершённые пары «вопрос → ответ».
  function buildHistory(prev: ChatTurn[]): Turn[] {
    const history: Turn[] = [];
    for (const t of prev) {
      if (!t.answer) continue;
      history.push({ role: "user", content: t.question });
      history.push({ role: "assistant", content: t.answer.answer });
    }
    return history;
  }

  async function handleSubmit({
    question,
    files,
  }: {
    question: string;
    files: File[];
  }) {
    if (loading) return;
    const typed = question.trim();
    const hasDoc = files.length > 0;
    if (!typed && !hasDoc) return;

    const display =
      typed || (hasDoc ? `Проверьте документ: ${files[0].name}` : "Вопрос");

    const history = buildHistory(turns);
    setTurns((prev) => [...prev, { question: display, answer: null, error: null }]);
    setLoading(true);

    const finish = (patch: Partial<ChatTurn>) =>
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, ...patch } : t)),
      );

    try {
      let attachmentText = "";
      for (const f of files) {
        const ext = await extractFile(f);
        if (ext.text) attachmentText += `\n\n[${f.name}]\n${ext.text}`;
      }

      const result = await ask({
        question: typed || DEFAULT_DOC_QUESTION,
        pipeline: PIPELINE,
        attachmentText: attachmentText.trim(),
        attachmentName: files[0]?.name ?? null,
        history,
      });
      finish({ answer: result });
    } catch (e) {
      finish({ error: e instanceof Error ? e.message : "Неизвестная ошибка" });
    } finally {
      setLoading(false);
    }
  }

  function resetConversation() {
    if (loading) return;
    setTurns([]);
  }

  return (
    <div className="flex min-h-screen flex-col">
      {/* Шапка */}
      <header className="mx-auto flex w-full max-w-content items-center justify-between px-5 py-5">
        <button
          type="button"
          onClick={resetConversation}
          className="text-subheading font-bold tracking-tight text-ink"
        >
          Enbek<span className="text-violet"> AI</span>
        </button>
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded-full border border-stone px-3.5 py-1.5 text-caption font-medium text-slate transition-colors hover:border-violet-washed hover:text-violet"
        >
          MCP на GitHub
          <span aria-hidden>→</span>
        </a>
      </header>

      <main className="mx-auto w-full max-w-content flex-1 px-5 pb-16">
        {/* Hero — только до начала диалога */}
        {!hasConversation && (
          <section className="pb-9 pt-12 text-center sm:pt-20">
            <h1 className="text-5xl font-bold tracking-tight text-ink sm:text-6xl">
              Enbek
              <span className="bg-sunburst bg-clip-text text-transparent"> AI</span>
            </h1>
            <p className="mx-auto mt-5 max-w-xl text-heading-sm font-medium leading-snug text-ink">
              Помощник по трудовому праву, трудовым отношениям и спорам в Казахстане
            </p>
            <p className="mx-auto mt-3 max-w-md text-subheading text-slate">
              Ответы со ссылками на Трудовой кодекс РК — за секунды.
            </p>
          </section>
        )}

        {/* Лента диалога */}
        {hasConversation && (
          <section className="space-y-5 pt-6">
            {turns.map((t, i) => {
              const isLast = i === turns.length - 1;
              return (
                <div key={i} className="space-y-4">
                  {/* Реплика пользователя */}
                  <div className="flex justify-end">
                    <div className="max-w-[85%] animate-fade-up rounded-3xl rounded-br-lg bg-violet px-4 py-2.5 text-body text-white shadow-sm motion-reduce:animate-none">
                      {t.question}
                    </div>
                  </div>

                  {/* Ответ / индикатор / ошибка */}
                  {t.answer && <AnswerCard result={t.answer} />}
                  {t.error && (
                    <div className="animate-fade-up rounded-2xl border border-orange/40 bg-orange/[0.06] p-4 text-body text-ink motion-reduce:animate-none">
                      <span className="font-semibold text-orange">Ошибка. </span>
                      {t.error}
                    </div>
                  )}
                  {isLast && loading && !t.answer && !t.error && <TypingIndicator />}
                </div>
              );
            })}
          </section>
        )}

        {/* Поле ввода */}
        <div className={hasConversation ? "mt-6" : "mt-0"}>
          <AskBox
            loading={loading}
            showExamples={!hasConversation}
            onSubmit={handleSubmit}
          />
        </div>

        {hasConversation && (
          <div className="mt-3 text-center">
            <button
              type="button"
              onClick={resetConversation}
              disabled={loading}
              className="text-caption text-slate underline underline-offset-2 transition-colors hover:text-violet disabled:opacity-40"
            >
              Новый диалог
            </button>
          </div>
        )}

        {/* Баннер MCP — только на стартовом экране */}
        {!hasConversation && (
          <section className="mt-14">
            <McpBanner />
          </section>
        )}
      </main>

      {/* Футер */}
      <footer className="mx-auto w-full max-w-content px-5 pb-10 text-center">
        <p className="text-caption text-ghost">
          Справочный сервис. Не является юридической консультацией.
        </p>
      </footer>
    </div>
  );
}
