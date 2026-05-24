const GITHUB_URL = "https://github.com/ti1ek/enbek-ai";

export default function McpBanner() {
  return (
    <a
      href={GITHUB_URL}
      target="_blank"
      rel="noopener noreferrer"
      className="group block overflow-hidden rounded-card border border-violet-washed bg-sunburst-soft p-5 transition-shadow hover:shadow-card sm:p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="text-2xl" aria-hidden>
            🛡️
          </span>
          <div>
            <p className="text-subheading font-medium text-ink">
              Enbek MCP-сервер
            </p>
            <p className="mt-1 max-w-xl text-body text-slate">
              Локальная маскировка персональных данных (ИИН, ФИО, телефоны) до
              отправки в LLM. Подключается к Claude Desktop. Open-source.
            </p>
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded bg-violet px-4 py-2 text-body font-medium text-white transition-colors group-hover:bg-violet-soft">
          Смотреть на GitHub
          <span aria-hidden className="transition-transform group-hover:translate-x-0.5">
            →
          </span>
        </span>
      </div>
    </a>
  );
}
