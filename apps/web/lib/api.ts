import type { ApiErrorBody } from "./types";

/** Browser-facing base path. The server-side proxy adds credentials. */
export const API_BASE = "/api/ff";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function apiUrl(path: string, query?: Record<string, string | number | undefined | null>): string {
  const clean = path.startsWith("/") ? path : `/${path}`;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  }
  const qs = params.toString();
  return `${API_BASE}${clean}${qs ? `?${qs}` : ""}`;
}

async function toError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // non-JSON error body
  }
  const err = (body as Partial<ApiErrorBody> | null)?.error;
  if (err && typeof err.message === "string") {
    return new ApiError(res.status, err.code ?? "error", err.message, err.details);
  }
  const detail = (body as { detail?: unknown } | null)?.detail;
  const message =
    typeof detail === "string" ? detail : `Request failed with status ${res.status} ${res.statusText}`.trim();
  return new ApiError(res.status, "http_error", message, detail);
}

export async function apiGet<T>(path: string, query?: Record<string, string | number | undefined | null>): Promise<T> {
  const res = await fetch(apiUrl(path, query), { headers: { accept: "application/json" }, cache: "no-store" });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    headers: { accept: "application/json", "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}
