"use client";

import { useEffect, useRef, useState } from "react";
import { ACCEPT_ATTR } from "@/lib/api";
import FileChip from "./FileChip";

export default function AskBox({
  loading,
  onSubmit,
}: {
  loading: boolean;
  onSubmit: (p: { question: string; files: File[] }) => void;
}) {
  const [question, setQuestion] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const canSubmit = !loading && (question.trim().length > 0 || files.length > 0);

  // Auto-grow textarea
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [question]);

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

  function submit(override?: string) {
    const typed = (override ?? question).trim();
    if (loading || (!typed && files.length === 0)) return;
    onSubmit({ question: typed, files });
    setQuestion("");
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (textareaRef.current) textareaRef.current.style.height = "auto";
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div>
      <div className="rounded-xl border border-parchment bg-snow shadow-sm transition-colors focus-within:border-stone">
        {/* File chips */}
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 px-4 pt-3">
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

        <textarea
          ref={textareaRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Спросите об увольнении, отпуске, зарплате, трудовом споре…"
          disabled={loading}
          className="w-full resize-none bg-transparent px-4 py-3.5 text-base text-ink outline-none placeholder:text-stone disabled:opacity-60"
        />

        <div className="flex items-center justify-between gap-3 px-3 py-2.5">
          {/* Attach button */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            aria-label="Прикрепить документ"
            title="Прикрепить документ (фото, скан, PDF, DOCX)"
            className="flex h-8 w-8 items-center justify-center rounded text-stone transition-colors hover:bg-parchment/60 hover:text-ink disabled:opacity-40"
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

          {/* Send button — claude-style dark circle */}
          <button
            type="button"
            onClick={() => submit()}
            disabled={!canSubmit}
            aria-label={loading ? "Идёт поиск" : "Отправить вопрос"}
            title="Отправить (Enter)"
            className={`
              flex h-8 w-8 items-center justify-center rounded-full transition-colors
              ${canSubmit
                ? "bg-ink text-snow hover:bg-onyx"
                : "bg-parchment text-stone cursor-not-allowed"
              }
            `}
          >
            {loading ? <Spinner /> : <ArrowUpIcon />}
          </button>
        </div>
      </div>

    </div>
  );
}

// Expose submit method for external callers (TopicChips → pick question)
export type { };

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function ArrowUpIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

function Spinner() {
  return (
    <span className="h-4 w-4 animate-spin rounded-full border-2 border-snow/30 border-t-snow" />
  );
}
