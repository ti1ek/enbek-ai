const GITHUB_URL = "https://github.com/ti1ek/enbek-ai";

export default function McpBanner() {
  return (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="group block overflow-hidden rounded-3xl border border-violet-washed bg-sunburst-soft p-6 transition-shadow hover:shadow-card sm:p-7"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3.5">
          <span className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-violet/10 text-violet">
            <ShieldIcon />
          </span>
          <div>
            <p className="text-subheading font-semibold text-ink">
              Enbek MCP-сервер
            </p>
            <p className="mt-1 max-w-xl text-body text-slate">
              Локальная маскировка персональных данных (ИИН, ФИО, телефоны) до
              отправки в LLM. Подключается к Claude Desktop. Open-source.
            </p>
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-violet px-5 py-2.5 text-body font-semibold text-white transition-colors group-hover:bg-violet-soft">
          Смотреть на GitHub
          <span
            aria-hidden
            className="transition-transform group-hover:translate-x-0.5"
          >
            →
          </span>
        </span>
      </div>
    </a>
  );
}

function ShieldIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
