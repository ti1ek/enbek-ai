"use client";

const GITHUB_URL = "https://github.com/ti1ek/enbek-ai/tree/main/mcp";

export interface ConversationMeta {
  id: string;
  title: string;
}

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  conversations: ConversationMeta[];
  activeId: string | null;
  onNew: () => void;
  onSelect: (id: string) => void;
}

export default function Sidebar({
  collapsed,
  onToggle,
  conversations,
  activeId,
  onNew,
  onSelect,
}: SidebarProps) {
  return (
    <>
      {/* Mobile backdrop */}
      {!collapsed && (
        <div
          className="fixed inset-0 z-20 bg-ink/20 sm:hidden"
          onClick={onToggle}
          aria-hidden
        />
      )}

      <aside
        className={`
          relative z-30 flex h-screen flex-col border-r border-parchment bg-[#f5f4ee]
          transition-[width] duration-200 ease-in-out
          ${collapsed ? "w-0 overflow-hidden sm:w-14" : "w-64"}
          fixed sm:static
        `}
      >
        {/* Top row: toggle + logo */}
        <div className="flex h-14 shrink-0 items-center gap-2.5 px-3">
          <button
            type="button"
            onClick={onToggle}
            aria-label={collapsed ? "Развернуть боковую панель" : "Свернуть боковую панель"}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded text-stone transition-colors hover:bg-parchment/70 hover:text-ink"
          >
            <PanelIcon />
          </button>
          {!collapsed && (
            <span className="truncate font-nunito text-[17px] font-black lowercase text-terra">
              enbek <span className="text-ink">ai</span>
            </span>
          )}
        </div>

        {/* New chat button */}
        <div className={`px-2 pb-2 ${collapsed ? "flex justify-center" : ""}`}>
          <button
            type="button"
            onClick={onNew}
            className={`
              flex items-center gap-2 rounded text-[13px] font-medium text-graphite
              transition-colors hover:bg-parchment/70 hover:text-ink
              ${collapsed ? "h-9 w-9 justify-center" : "w-full px-3 py-2"}
            `}
            title="Новый чат"
          >
            <PlusIcon />
            {!collapsed && <span>Новый чат</span>}
          </button>
        </div>

        {/* MCP block — right after New chat, prominent */}
        {!collapsed && (
          <div className="mx-2 mb-3">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-start gap-2.5 rounded-[9.6px] border border-terra/25 bg-terra/[0.06] p-3 transition-colors hover:border-terra/40 hover:bg-terra/[0.10]"
            >
              <span className="mt-0.5 shrink-0 text-terra">
                <ShieldIcon />
              </span>
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-ink">enbek MCP</p>
                <p className="mt-0.5 text-[11px] leading-snug text-dusty">
                  Конфиденциальные данные не уходят в ИИ — скрываем автоматически
                </p>
              </div>
              <span className="ml-auto shrink-0 text-stone transition-transform group-hover:translate-x-0.5">
                <ArrowIcon />
              </span>
            </a>
          </div>
        )}
        {collapsed && (
          <div className="flex justify-center px-2 pb-2">
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              title="Enbek MCP"
              className="flex h-9 w-9 items-center justify-center rounded text-terra transition-colors hover:bg-terra/10"
            >
              <ShieldIcon />
            </a>
          </div>
        )}

        {/* Recents — fills remaining space, always pushes footer down */}
        <div className="flex-1 overflow-y-auto">
          {!collapsed && conversations.length > 0 && (
            <div className="px-2 pb-2">
              <p className="px-3 pb-1.5 pt-3 text-[11px] font-medium uppercase tracking-wider text-stone">
                Недавние
              </p>
              <ul className="space-y-0.5">
                {conversations.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(c.id)}
                      className={`
                        w-full truncate rounded px-3 py-2 text-left text-[13px] transition-colors
                        ${c.id === activeId
                          ? "bg-parchment/80 text-ink"
                          : "text-graphite hover:bg-parchment/50 hover:text-ink"
                        }
                      `}
                      title={c.title}
                    >
                      {c.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Footer */}
        {!collapsed && (
          <div className="shrink-0 border-t border-parchment px-3 py-4">
            <p className="text-[11px] leading-snug text-stone">
              Справочный сервис. Не является юридической консультацией.
            </p>
          </div>
        )}
      </aside>
    </>
  );
}

function PanelIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M9 3v18" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}
