"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { AskResponse, Source } from "@/lib/api";

// Номер статьи/пункта вида «92», «31-1» — показываем; внутренние id («block_5»,
// «31_5») и длинные заголовки разделов — нет (опираемся на название документа).
const NUM_RE = /^\d+(?:[-/]\d+)*$/;

// Известные документы на adilet.zan.kz по doc-id.
const ADILET_DOCS: Record<string, { name: string; type: string }> = {
  K1500000414: { name: "Трудовой кодекс РК",    type: "labor_code"  },
  K2300000224: { name: "Социальный кодекс РК",  type: "social_code" },
  K1400000235: { name: "КоАП РК",               type: "koap"        },
  K990000409_: { name: "Гражданский кодекс РК", type: "civil_code"  },
};

// Создать минимальную Source-запись для URL из ответа, которого нет в sources[].
// Модель иногда цитирует статьи из своих знаний (не из retrieved-контекста),
// используя корректный паттерн adilet-ссылки — их нужно показать в панели.
function inferSource(url: string): Source | null {
  // adilet.zan.kz/rus/docs/DOCID#zNN
  const am = url.match(
    /adilet\.zan\.kz\/rus\/docs\/([A-Z0-9_]+)(?:#z(\d+(?:-\d+)*))?/,
  );
  if (am) {
    const meta = ADILET_DOCS[am[1]];
    const art = am[2] && am[2] !== "0" ? am[2] : null;
    return {
      url,
      doc_name: meta?.name ?? "Нормативный акт РК",
      source_type: meta?.type ?? null,
      article: art,
    };
  }
  // tkrk.kz/.../statya-NN
  const tm = url.match(/tkrk\.kz\/.*\/statya-(\d+)/);
  if (tm)
    return {
      url,
      doc_name: "Комментарий к ТК РК",
      source_type: "labor_code_commentary",
      article: tm[1],
    };
  // dialog.egov.kz
  if (url.includes("dialog.egov.kz"))
    return { url, doc_name: "Разъяснение Минтруда РК", source_type: "mintrud_dialog" };
  // Любой другой https — покажем как есть
  return { url };
}

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

  // Шаг 1: из sources[] оставляем только процитированные в тексте (без дублей).
  const citedUrls = new Set<string>();
  const citedSources = (result.sources ?? []).filter((s) => {
    if (!s.url || !answer.includes(s.url)) return false;
    if (citedUrls.has(s.url)) return false;
    citedUrls.add(s.url);
    return true;
  });

  // Шаг 2: модель иногда использует URL из своих знаний (паттерн adilet известен
  // из обучения), которых нет в retrieved sources[]. Добираем их как inferred-записи.
  const allAnswerUrls = Array.from(
    new Set(
      Array.from(answer.matchAll(/\]\((https?:\/\/[^)]+)\)/g)).map((m) => m[1]),
    ),
  );
  const inferredSources: Source[] = allAnswerUrls
    .filter((u) => !citedUrls.has(u))
    .map(inferSource)
    .filter((s): s is Source => s !== null);

  const sources = [...citedSources, ...inferredSources];

  return (
    <article className="animate-fade-up rounded-3xl border border-stone bg-surface p-5 shadow-card motion-reduce:animate-none sm:p-7">
      <div className="answer-prose">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            // Ссылки на adilet.zan.kz и др. открываем в новой вкладке,
            // чтобы пользователь не уходил с сайта.
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
    </article>
  );
}
