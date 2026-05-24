"use client";

function humanSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

export default function FileChip({
  file,
  onRemove,
  disabled,
}: {
  file: File;
  onRemove: () => void;
  disabled?: boolean;
}) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-violet-washed bg-violet/[0.04] py-1 pl-3 pr-1.5 text-caption text-ink">
      <span aria-hidden>📎</span>
      <span className="max-w-[180px] truncate" title={file.name}>
        {file.name}
      </span>
      <span className="text-ghost">{humanSize(file.size)}</span>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Убрать ${file.name}`}
        className="flex h-4 w-4 items-center justify-center rounded-full text-ghost transition-colors hover:bg-stone/60 hover:text-ink disabled:opacity-40"
      >
        ✕
      </button>
    </span>
  );
}
