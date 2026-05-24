"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AskResponse, Source } from "@/lib/api";

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

  const seenUrls = new Set<string>();
  const sources = (result.sources ?? []).filter((s) => {
    if (!s.url || !answer.includes(s.url)) return false;
    if (seenUrls.has(s.url)) return false;
    seenUrls.add(s.url);
    return true;
  });

  return (
    <article className="animate-fade-up motion-reduce:animate-none">
      {/* Plain prose — no card, no border, just text on vellum */}
      <div className="answer-prose">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children, ...props }) => (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                {children}
              </a>
            ),
          }}
        >
          {result.answer}
        </ReactMarkdown>
      </div>

      {sources.length > 0 && (
        <div className="mt-5 border-t border-parchment pt-4">
          <h3 className="mb-2.5 text-[11px] font-medium uppercase tracking-wider text-stone">
            Источники
          </h3>
          <ul className="space-y-1.5">
            {sources.map((s, i) => (
              <li key={i} className="flex items-baseline gap-2 text-[13px]">
                <span className="shrink-0 text-terra">§</span>
                <a
                  href={s.url!}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#2563eb] underline underline-offset-2 transition-opacity hover:opacity-75"
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
