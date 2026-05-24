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
        <span className="text-subheading font-bold tracking-tight text-ink">
          Enbek<span className="text-violet"> AI</span>
        </span>
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
        {/* Hero */}
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

        {/* Поле ввода */}
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

        {/* Ошибка */}
        {error && (
          <div className="mt-6 rounded-2xl border border-orange/40 bg-orange/[0.06] p-4 text-body text-ink">
            <span className="font-semibold text-orange">Ошибка. </span>
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
        <section className="mt-14">
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
