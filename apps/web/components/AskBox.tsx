"use client";

import { useRef, useState } from "react";
import { ACCEPT_ATTR, ask, extractFile, type AskResponse } from "@/lib/api";
import FileChip from "./FileChip";

// Лучший по эвалу пайплайн — используется всегда.
const PIPELINE = "advanced" as const;

const DEFAULT_DOC_QUESTION =
  "Проанализируй приложенный документ на соответствие трудовому праву РК.";

const EXAMPLES = [
  "Сколько дней ежегодного отпуска по ТК РК?",
  "Как уволиться по соглашению сторон?",
  "Что делать при задержке зарплаты?",
  "Положена ли компенсация при сокращении?",
];

export default function AskBox({
  loading,
  onStart,
  onResult,
  onError,
}: {
  loading: boolean;
  onStart: () => void;
  onResult: (r: AskResponse) => void;
  onError: (msg: string) => void;
}) {
  const [question, setQuestion] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canSubmit = !loading && (question.trim().length > 0 || files.length > 0);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const incoming = Array.from(list);
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...incoming.filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function submit(override?: string) {
    const typed = (override ?? question).trim();
    if (loading || (!typed && files.length === 0)) return;
    onStart();
    try {
      let attachmentText = "";
      for (const f of files) {
        const ext = await extractFile(f);
        if (ext.text) attachmentText += `\n\n[${f.name}]\n${ext.text}`;
      }

      const q = typed || DEFAULT_DOC_QUESTION;

      const result = await ask({
        question: q,
        pipeline: PIPELINE,
        attachmentText: attachmentText.trim(),
        attachmentName: files[0]?.name ?? null,
      });
      onResult(result);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Неизвестная ошибка");
    }
  }

  function onExample(text: string) {
    setQuestion(text);
    void submit(text);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void submit();
    }
  }

  return (
    <div>
      <div className="rounded-[28px] border border-stone bg-surface p-3.5 shadow-sm transition-shadow focus-within:border-violet-washed focus-within:shadow-card">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          rows={3}
          placeholder="Спросите об увольнении, отпуске, зарплате, трудовом споре…"
          disabled={loading}
          className="w-full resize-none bg-transparent px-3 py-2 text-subheading text-ink outline-none placeholder:text-ghost disabled:opacity-60"
        />

        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 px-1.5 pb-2 pt-1">
            {files.map((f, i) => (
              <FileChip
                key={`${f.name}:${f.size}`}
                file={f}
                onRemove={() => removeFile(i)}
                disabled={loading}
              />
            ))}
          </div>
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            aria-label="Прикрепить документ"
            title="Прикрепить документ (фото, скан, PDF, DOCX)"
            className="flex h-10 w-10 items-center justify-center rounded-full text-slate transition-colors hover:bg-powder hover:text-violet disabled:opacity-40"
          >
            <PaperclipIcon />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT_ATTR}
            multiple
            onChange={(e) => addFiles(e.target.files)}
            className="hidden"
          />

          <button
            type="button"
            onClick={() => submit()}
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 rounded-full bg-violet px-6 py-3 text-body font-semibold text-white transition-colors hover:bg-violet-soft disabled:cursor-not-allowed disabled:opacity-40"
          >
            {loading ? (
              <>
                <Spinner />
                Ищу…
              </>
            ) : (
              <>
                Спросить
                <ArrowIcon />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Примеры-вопросы */}
      <div className="mt-3.5 flex flex-wrap justify-center gap-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            onClick={() => onExample(ex)}
            disabled={loading}
            className="rounded-full border border-stone bg-surface px-3.5 py-1.5 text-caption text-slate transition-colors hover:border-violet-washed hover:text-violet disabled:opacity-40"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

function PaperclipIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function Spinner() {
  return (
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
  );
}
