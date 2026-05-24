"use client";

import { useState } from "react";

interface Topic {
  id: string;
  label: string;
  icon: React.ReactNode;
  questions: string[];
}

const TOPICS: Topic[] = [
  {
    id: "dismissal",
    label: "Увольнение",
    icon: <BriefcaseIcon />,
    questions: [
      "Как уволиться по соглашению сторон?",
      "Какой срок отработки при увольнении по собственному желанию?",
      "Положена ли компенсация при сокращении штата?",
      "Могут ли уволить во время больничного?",
    ],
  },
  {
    id: "vacation",
    label: "Отпуск",
    icon: <SunIcon />,
    questions: [
      "Сколько дней ежегодного отпуска по ТК РК?",
      "Как рассчитывается отпускная компенсация?",
      "Можно ли разделить отпуск на части?",
      "Как оформить отпуск без сохранения зарплаты?",
    ],
  },
  {
    id: "salary",
    label: "Зарплата",
    icon: <CoinIcon />,
    questions: [
      "Что делать при задержке зарплаты?",
      "Каков размер минимальной заработной платы в РК?",
      "Как оплачивается сверхурочная работа?",
      "Законно ли удержание из зарплаты?",
    ],
  },
  {
    id: "contract",
    label: "Трудовой договор",
    icon: <DocumentIcon />,
    questions: [
      "Что обязательно должно быть в трудовом договоре?",
      "Можно ли заключать срочный трудовой договор?",
      "Каков максимальный срок испытательного срока?",
    ],
  },
  {
    id: "hours",
    label: "Рабочее время",
    icon: <ClockIcon />,
    questions: [
      "Какова норма рабочего времени в неделю?",
      "Как оплачивается работа в праздничные дни?",
      "Положен ли обеденный перерыв по закону?",
    ],
  },
];

export default function TopicChips({ onPick }: { onPick: (q: string) => void }) {
  const [activeId, setActiveId] = useState<string | null>(null);

  const activeTopic = TOPICS.find((t) => t.id === activeId) ?? null;

  function toggle(id: string) {
    setActiveId((prev) => (prev === id ? null : id));
  }

  return (
    <div className="mt-2">
      {/* Pills row */}
      <div className="flex flex-wrap justify-center gap-2">
        {TOPICS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => toggle(t.id)}
            className={`
              inline-flex items-center gap-1.5 rounded border px-3.5 py-1.5
              text-[13px] font-medium transition-colors
              ${activeId === t.id
                ? "border-terra/40 bg-terra/[0.07] text-terra"
                : "border-parchment bg-snow text-graphite hover:border-terra/30 hover:text-ink"
              }
            `}
          >
            <span className="opacity-70">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {/* Expanded questions */}
      {activeTopic && (
        <div className="mx-auto mt-3 max-w-content animate-fade-up rounded-card border border-parchment bg-snow p-4">
          <ul className="space-y-1">
            {activeTopic.questions.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  onClick={() => { setActiveId(null); onPick(q); }}
                  className="w-full rounded px-3 py-2 text-left text-[14px] text-graphite transition-colors hover:bg-parchment/50 hover:text-ink"
                >
                  {q}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function BriefcaseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="2" y="7" width="20" height="14" rx="2" />
      <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
      <path d="M12 12v.01" />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function CoinIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <path d="M14.8 9A2 2 0 0 0 13 8h-2a2 2 0 0 0 0 4h2a2 2 0 0 1 0 4h-2a2 2 0 0 1-1.8-1" />
      <path d="M12 6v2m0 8v2" />
    </svg>
  );
}

function DocumentIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="16" y2="17" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15 15" />
    </svg>
  );
}

