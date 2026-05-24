"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AskResponse, Source } from "@/lib/api";

function sourceLabel(s: Source): string {
  const parts = [s.doc_name, s.article, s.paragraph].filter(Boolean);
  return parts.length ? parts.join(" · ") : s.source_type || s.url || "Источник";
}

export default function AnswerCard({ result }: { result: AskResponse }) {
  const sources = result.sources?.filter(
    (s) => s.doc_name || s.article || s.url || s.source_type,
  );

  return (
    <article className="rounded-card border border-stone bg-surface p-5 shadow-card sm:p-6">
      <div className="answer-prose">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {result.answer}
        </ReactMarkdown>
      </div>

      {sources && sources.length > 0 && (
        <div className="mt-5 border-t border-stone pt-4">
          <h3 className="mb-2 text-caption font-medium uppercase tracking-wide text-ghost">
            Источники
          </h3>
          <ul className="space-y-1.5">
            {sources.map((s, i) => {
              const label = sourceLabel(s);
              return (
                <li key={i} className="text-body text-slate">
                  <span className="mr-2 text-violet">§</span>
                  {s.url ? (
                    <a
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-violet underline underline-offset-2 hover:text-violet-soft"
                    >
                      {label}
                    </a>
                  ) : (
                    label
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <p className="mt-4 text-caption text-ghost">
        ⏱ {result.latency_ms} мс · {result.pipeline.toUpperCase()} RAG
      </p>
    </article>
  );
}
