"use client";

import { useState } from "react";
import AskBox from "@/components/AskBox";
import AnswerCard from "@/components/AnswerCard";
import McpBanner from "@/components/McpBanner";
import type { AskResponse } from "@/lib/api";

const GITHUB_URL = "https://github.com/ti1ek/enbek-ai";

export default function Home() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <div className="flex min-h-screen flex-col">
      {/* Шапка */}
      <header className="mx-auto flex w-full max-w-content items-center justify-between px-5 py-5">
        <span className="flex items-center gap-2 text-subheading font-medium text-ink">
          <span aria-hidden>⚖️</span>
          Enbek&nbsp;AI
        </span>
        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1.5 rounded border border-violet-washed px-3 py-1.5 text-caption font-medium text-violet transition-colors hover:bg-violet/[0.05]"
        >
          <span aria-hidden>🛡️</span>
          MCP на GitHub
          <span aria-hidden>→</span>
        </a>
      </header>

      <main className="mx-auto w-full max-w-content flex-1 px-5 pb-16">
        {/* Hero */}
        <section className="pb-8 pt-10 text-center sm:pt-16">
          <h1 className="text-heading-lg font-light text-ink sm:text-display">
            Enbek AI
          </h1>
          <p className="mt-3 text-subheading text-slate">
            AI-ассистент по трудовому праву РК
          </p>
          <p className="mx-auto mt-4 max-w-lg text-heading-sm font-light text-ink">
            Трудовое право Казахстана —{" "}
            <span className="bg-sunburst bg-clip-text text-transparent">
              простыми словами
            </span>
            , со ссылками на закон.
          </p>
        </section>

        {/* Поле ввода */}
        <section>
          <AskBox
            loading={loading}
            onStart={() => {
              setLoading(true);
              setError(null);
            }}
            onResult={(r) => {
              setResult(r);
              setLoading(false);
            }}
            onError={(msg) => {
              setError(msg);
              setLoading(false);
            }}
          />
          <p className="mt-2 px-1 text-caption text-ghost">
            Можно прикрепить трудовой договор или приказ — фото, скан, PDF, DOCX.
            Система извлечёт текст и учтёт его при ответе.
          </p>
        </section>

        {/* Ошибка */}
        {error && (
          <div className="mt-6 rounded border border-orange/40 bg-orange/[0.06] p-4 text-body text-ink">
            <span className="font-medium text-orange">Ошибка. </span>
            {error}
          </div>
        )}

        {/* Ответ */}
        {result && (
          <section className="mt-6">
            <AnswerCard result={result} />
          </section>
        )}

        {/* Баннер MCP */}
        <section className="mt-12">
          <McpBanner />
        </section>
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
