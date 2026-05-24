const GITHUB_URL = "https://github.com/ti1ek/enbek-ai";

export default function McpBanner() {
  return (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="group block overflow-hidden rounded-card border border-parchment bg-[#f5f4ee] p-5 transition-colors hover:border-stone/60 sm:p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded border border-parchment bg-snow text-terra">
            <ShieldIcon />
          </span>
          <div>
            <p className="text-[15px] font-medium text-ink">Enbek MCP-сервер</p>
            <p className="mt-0.5 max-w-sm text-[13px] leading-relaxed text-dusty">
              Локальная маскировка персональных данных до отправки в LLM. Подключается к Claude Desktop.
            </p>
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded border border-parchment bg-snow px-4 py-2 text-[13px] font-medium text-graphite transition-colors group-hover:border-stone/60 group-hover:text-ink">
          Смотреть на GitHub
          <span aria-hidden className="transition-transform group-hover:translate-x-0.5">→</span>
        </span>
      </div>
    </a>
  );
}

function ShieldIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
