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
    <span className="inline-flex items-center gap-1.5 rounded border border-parchment bg-[#f0eee6] py-1 pl-2.5 pr-1.5 text-[12px] text-ink">
      <PaperclipIcon />
      <span className="max-w-[160px] truncate" title={file.name}>
        {file.name}
      </span>
      <span className="text-stone">{humanSize(file.size)}</span>
      <button
        type="button"
        onClick={onRemove}
        disabled={disabled}
        aria-label={`Убрать ${file.name}`}
        className="flex h-4 w-4 items-center justify-center rounded text-stone transition-colors hover:bg-parchment hover:text-ink disabled:opacity-40"
      >
        <XIcon />
      </button>
    </span>
  );
}

function PaperclipIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}
