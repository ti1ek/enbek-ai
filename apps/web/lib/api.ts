// Клиент к FastAPI-бэкенду Enbek AI (/api/v1/ask, /api/v1/extract).
// Повторяет логику apps/stub_ui/app.py.

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
  "http://localhost:8000/api/v1";

export type Pipeline = "advanced" | "basic";

export const ATTACH_TYPES = [
  "png",
  "jpg",
  "jpeg",
  "webp",
  "pdf",
  "docx",
  "txt",
  "md",
] as const;

export const ACCEPT_ATTR = ATTACH_TYPES.map((t) => `.${t}`).join(",");

export interface ExtractResponse {
  filename: string;
  text: string;
  method: string;
  pages: number;
  chars: number;
  truncated: boolean;
}

export interface Source {
  source_type?: string | null;
  doc_name?: string | null;
  article?: string | null;
  paragraph?: string | null;
  url?: string | null;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  classification?: string | null;
  latency_ms: number;
  cost_usd: number;
  pipeline: string;
}

async function detail(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return data.detail;
    return JSON.stringify(data?.detail ?? data);
  } catch {
    return res.statusText;
  }
}

/** Отправить файл на /extract и получить извлечённый текст. */
export async function extractFile(file: File): Promise<ExtractResponse> {
  const form = new FormData();
  form.append("file", file, file.name);

  const res = await fetch(`${API_BASE}/extract`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) {
    throw new Error(
      `Не удалось извлечь «${file.name}»: ${res.status} ${await detail(res)}`,
    );
  }
  return res.json();
}

/** Задать вопрос на /ask. */
export async function ask(params: {
  question: string;
  pipeline: Pipeline;
  attachmentText?: string;
  attachmentName?: string | null;
}): Promise<AskResponse> {
  const res = await fetch(`${API_BASE}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: params.question,
      pipeline: params.pipeline,
      attachment_text: params.attachmentText ?? "",
      attachment_name: params.attachmentName ?? null,
    }),
  });
  if (!res.ok) {
    throw new Error(`Ошибка API ${res.status}: ${await detail(res)}`);
  }
  return res.json();
}
