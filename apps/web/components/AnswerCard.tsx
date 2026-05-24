"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AskResponse, Source } from "@/lib/api";

// Номер статьи/пункта вида «92», «31-1» — показываем; внутренние id («block_5»,
// «31_5») и длинные заголовки разделов — нет (опираемся на название документа).
const NUM_RE = /^\d+(?:[-/]\d+)*$/;

function sourceLabel(s: Source): string {
  const rawArt = (s.article || "").trim();
  const article = NUM_RE.test(rawArt) && rawArt !== "0" ? `ст. ${rawArt}` : null;
  const rawPara = (s.paragraph || "").trim();
  const paragraph = NUM_RE.test(rawPara) ? `п. ${rawPara}` : null;
  const parts = [s.doc_name, article, paragraph].filter(Boolean);
  return parts.length ? parts.join(" · ") : s.source_type || s.url || "Источник";
}

export default function AnswerCard({ result }: { result: AskResponse }) {
  const answer = result.answer ?? "";

  // Показываем только источники, чей URL реально процитирован в тексте ответа.
  // Модель работает в строгом RAG-режиме и не генерирует URL из своих знаний,
  // поэтому панель всегда соответствует inline-ссылкам один-в-один.
  const seenUrls = new Set<string>();
  const sources = (result.sources ?? []).filter((s) => {
    if (!s.url || !answer.includes(s.url)) return false;
    if (seenUrls.has(s.url)) return false;
    seenUrls.add(s.url);
    return true;
  });

  return (
    <article className="animate-fade-up rounded-3xl border border-stone bg-surface p-5 shadow-card motion-reduce:animate-none sm:p-7">
      <div className="answer-prose">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children, ...props }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                {...props}
              >
                {children}
              </a>
            ),
          }}
        >
          {result.answer}
        </ReactMarkdown>
      </div>

      {sources.length > 0 && (
        <div className="mt-5 border-t border-stone pt-4">
          <h3 className="mb-2 text-caption font-medium uppercase tracking-wide text-ghost">
            Источники
          </h3>
          <ul className="space-y-1.5">
            {sources.map((s, i) => (
              <li key={i} className="text-body text-slate">
                <span className="mr-2 text-violet">§</span>
                <a
                  href={s.url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-violet underline underline-offset-2 hover:text-violet-soft"
                >
                  {sourceLabel(s)}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}
