"use client";

import { useRef, useState } from "react";
import {
  ACCEPT_ATTR,
  ask,
  extractFile,
  type AskResponse,
  type Pipeline,
} from "@/lib/api";
import FileChip from "./FileChip";

const DEFAULT_DOC_QUESTION =
  "Проанализируй приложенный документ на соответствие трудовому праву РК.";

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
  const [pipeline, setPipeline] = useState<Pipeline>("advanced");
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

  async function submit() {
    if (!canSubmit) return;
    onStart();
    try {
      // 1. Извлечь текст из вложений
      let attachmentText = "";
      for (const f of files) {
        const ext = await extractFile(f);
        if (ext.text) attachmentText += `\n\n[${f.name}]\n${ext.text}`;
      }

      // 2. Если вопроса нет, но есть документ — дефолтный промпт
      const q = question.trim() || (files.length ? DEFAULT_DOC_QUESTION : "");

      // 3. Спросить
      const result = await ask({
        question: q,
        pipeline,
        attachmentText: attachmentText.trim(),
        attachmentName: files[0]?.name ?? null,
      });
      onResult(result);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Неизвестная ошибка");
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void submit();
    }
  }

  return (
    <div className="rounded-card border border-stone bg-surface p-3 shadow-sm transition-shadow focus-within:shadow-card">
      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={onKeyDown}
        rows={3}
        placeholder="Спросите или прикрепите документ…"
        disabled={loading}
        className="w-full resize-none bg-transparent px-2 py-1.5 text-subheading text-ink outline-none placeholder:text-ghost disabled:opacity-60"
      />

      {files.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1 pb-2 pt-1">
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

      <div className="flex items-center justify-between gap-3 border-t border-stone/70 pt-2.5">
        <div className="flex items-center gap-2">
          {/* Прикрепить файл */}
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={loading}
            aria-label="Прикрепить документ"
            title="Прикрепить документ (фото, скан, PDF, DOCX)"
            className="flex h-9 w-9 items-center justify-center rounded text-lg text-slate transition-colors hover:bg-powder hover:text-violet disabled:opacity-40"
          >
            📎
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPT_ATTR}
            multiple
            onChange={(e) => addFiles(e.target.files)}
            className="hidden"
          />

          {/* Переключатель режима */}
          <div className="flex items-center rounded bg-powder p-0.5 text-caption">
            {(["advanced", "basic"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setPipeline(mode)}
                disabled={loading}
                className={`rounded px-2.5 py-1 font-medium transition-colors disabled:opacity-50 ${
                  pipeline === mode
                    ? "bg-surface text-violet shadow-sm"
                    : "text-ghost hover:text-slate"
                }`}
              >
                {mode === "advanced" ? "Точный" : "Быстрый"}
              </button>
            ))}
          </div>
        </div>

        {/* Отправить */}
        <button
          type="button"
          onClick={submit}
          disabled={!canSubmit}
          className="inline-flex items-center gap-2 rounded bg-violet px-5 py-2.5 text-body font-medium text-white transition-colors hover:bg-violet-soft disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? (
            <>
              <Spinner />
              Ищу…
            </>
          ) : (
            <>
              Спросить
              <span aria-hidden>→</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

function Spinner() {
  return (
    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
  );
}
