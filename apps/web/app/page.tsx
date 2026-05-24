"use client";

import { useEffect, useRef, useState } from "react";
import AskBox from "@/components/AskBox";
import AnswerCard from "@/components/AnswerCard";
import TypingIndicator from "@/components/TypingIndicator";
import Sidebar, { type ConversationMeta } from "@/components/Sidebar";
import TopicChips from "@/components/TopicChips";
import { ask, extractFile, type AskResponse, type Turn } from "@/lib/api";

const PIPELINE = "advanced" as const;
const DEFAULT_DOC_QUESTION = "Проанализируй приложенный документ на соответствие трудовому праву РК.";

interface ChatTurn {
  question: string;
  answer: AskResponse | null;
  error: string | null;
}

interface Conversation {
  id: string;
  title: string;
  turns: ChatTurn[];
}

function newId() {
  return Math.random().toString(36).slice(2);
}

function buildHistory(turns: ChatTurn[]): Turn[] {
  const history: Turn[] = [];
  for (const t of turns) {
    if (!t.answer) continue;
    history.push({ role: "user", content: t.question });
    history.push({ role: "assistant", content: t.answer.answer });
  }
  return history;
}

export default function Home() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const activeConv = conversations.find((c) => c.id === activeId) ?? null;
  const turns = activeConv?.turns ?? [];
  const hasMessages = turns.length > 0;

  // Scroll to bottom when turns change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function handleSubmit({ question, files }: { question: string; files: File[] }) {
    if (loading) return;
    const typed = question.trim();
    const hasDoc = files.length > 0;
    if (!typed && !hasDoc) return;

    const display = typed || (hasDoc ? `Проверьте документ: ${files[0].name}` : "Вопрос");

    // Create new conversation if none active
    let convId = activeId;
    if (!convId || !conversations.find((c) => c.id === convId)) {
      const id = newId();
      const newConv: Conversation = { id, title: display.slice(0, 60), turns: [] };
      setConversations((prev) => [newConv, ...prev]);
      setActiveId(id);
      convId = id;
    }

    // Derive history from current turns before adding new one
    const currentTurns = conversations.find((c) => c.id === convId)?.turns ?? turns;
    const history = buildHistory(currentTurns);

    // Add optimistic user turn
    const newTurn: ChatTurn = { question: display, answer: null, error: null };
    setConversations((prev) =>
      prev.map((c) => c.id === convId ? { ...c, turns: [...c.turns, newTurn] } : c)
    );
    setLoading(true);

    function finish(patch: Partial<ChatTurn>) {
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id !== convId) return c;
          const t = [...c.turns];
          t[t.length - 1] = { ...t[t.length - 1], ...patch };
          return { ...c, turns: t };
        })
      );
    }

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

  function handleNew() {
    if (loading) return;
    setActiveId(null);
  }

  function handleSelect(id: string) {
    setActiveId(id);
  }

  const sidebarMeta: ConversationMeta[] = conversations.map((c) => ({
    id: c.id,
    title: c.title,
  }));

  return (
    <div className="flex h-screen overflow-hidden bg-vellum">
      {/* Sidebar */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed((v) => !v)}
        conversations={sidebarMeta}
        activeId={activeId}
        onNew={handleNew}
        onSelect={handleSelect}
      />

      {/* Main area */}
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {hasMessages ? (
          /* ── Chat screen ── */
          <>
            {/* Scrollable messages */}
            <div className="flex-1 overflow-y-auto">
              <div className="mx-auto max-w-content space-y-8 px-5 py-10">
                {turns.map((t, i) => {
                  const isLast = i === turns.length - 1;
                  return (
                    <div key={i} className="space-y-5">
                      {/* User message — soft bubble right-aligned */}
                      <div className="flex justify-end">
                        <div className="max-w-[80%] animate-fade-up rounded-[18px] border border-parchment bg-[#f0eee6] px-4 py-2.5 text-base text-ink motion-reduce:animate-none">
                          {t.question}
                        </div>
                      </div>

                      {/* Assistant reply */}
                      {t.answer && <AnswerCard result={t.answer} />}
                      {t.error && (
                        <div className="animate-fade-up rounded border border-parchment bg-[#f5f4ee] p-4 text-base motion-reduce:animate-none">
                          <span className="font-medium text-terra">Ошибка. </span>
                          <span className="text-graphite">{t.error}</span>
                        </div>
                      )}
                      {isLast && loading && !t.answer && !t.error && <TypingIndicator />}
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Sticky input at bottom */}
            <div className="relative shrink-0">
              <div className="pointer-events-none absolute -top-8 left-0 right-0 h-8 bg-gradient-to-t from-vellum" />
              <div className="mx-auto max-w-content px-5 pb-7 pt-1">
                <AskBox loading={loading} onSubmit={handleSubmit} />
              </div>
            </div>
          </>
        ) : (
          /* ── Start screen ── */
          <div className="flex flex-1 flex-col items-center overflow-y-auto px-5">
            {/* pt фиксирован — инпут никогда не прыгает при раскрытии чипов */}
            <div className="w-full max-w-content pt-[28vh]">
              <div className="mb-6 text-center">
                <h1 className="font-serif text-[22px] font-medium leading-tight tracking-tight text-ink sm:text-[26px]">
                  Ваш AI-помощник по Трудовому кодексу РК
                </h1>
              </div>
              <AskBox loading={loading} onSubmit={handleSubmit} />
              {/* Chips вплотную под инпутом */}
              <TopicChips
                onPick={(q) => handleSubmit({ question: q, files: [] })}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
