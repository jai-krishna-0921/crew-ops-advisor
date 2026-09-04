/**
 * The one place the web app talks to anything.
 *
 * `NEXT_PUBLIC_USE_MOCKS=1` swaps the whole data layer for the fixtures in
 * `src/mocks/`. Nothing else in the application knows which side it is on, so
 * when the backend lands, flipping the flag is the only change.
 *
 * The app contains no answering logic. Every function here either fetches a
 * shape the API computed or returns a fixture of that same shape.
 */

import type {
  ChatRequest,
  CoverRequest,
  HealthResponse,
  ImpactReport,
  LegalityReport,
  LegalityRequest,
  Recommendation,
  Reply,
  RuleDefinition,
  SampleQuestion,
  SimulateRequest,
  StreamEvent,
  ThreadDetail,
  ThreadSummary,
  Watchlist,
  WorldSummary,
} from "@/lib/contracts";
import { streamChat, type StreamError } from "@/lib/sse";

import { WATCHLIST } from "@/mocks/brief";
import { LEGALITY_BY_CREW } from "@/mocks/legality";
import { IMPACT, pickReply, RECOMMENDATION, REPLIES } from "@/mocks/replies";
import { playScript, scriptFor } from "@/mocks/stream";
import { HEALTH, QUESTIONS, RULES, THREADS, WORLD } from "@/mocks/world";

export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** Playback speed for the mock stream. 1 is realistic, higher is faster. */
const MOCK_SPEED = Number(process.env.NEXT_PUBLIC_MOCK_SPEED ?? "1") || 1;

class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function get<T>(path: string, fallback: T): Promise<T> {
  if (USE_MOCKS) return delay(fallback);
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(
      `GET ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

async function post<T>(path: string, body: unknown, fallback: T): Promise<T> {
  if (USE_MOCKS) return delay(fallback);
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new ApiError(
      `POST ${path} failed: ${response.status} ${response.statusText}`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms / MOCK_SPEED));
}

/* ---------------------------------------------------------------- routes */

export const api = {
  health: () => get<HealthResponse>("/api/health", HEALTH),

  worldSummary: () => get<WorldSummary>("/api/world/summary", WORLD),

  rules: () => get<RuleDefinition[]>("/api/rules", RULES),

  questions: () => get<SampleQuestion[]>("/api/questions", QUESTIONS),

  threads: () => get<ThreadSummary[]>("/api/threads", THREADS),

  thread: (id: string) =>
    get<ThreadDetail>(`/api/threads/${encodeURIComponent(id)}`, {
      thread_id: id,
      title: THREADS.find((t) => t.thread_id === id)?.title ?? "Thread",
      created_at: THREADS.find((t) => t.thread_id === id)?.created_at ?? "",
      turns: [],
    }),

  brief: (date: string) =>
    get<Watchlist>(`/api/brief?date=${encodeURIComponent(date)}`, WATCHLIST),

  simulate: (request: SimulateRequest) =>
    post<ImpactReport>("/api/simulate", request, IMPACT),

  legality: (request: LegalityRequest) =>
    post<LegalityReport>(
      "/api/legality",
      request,
      LEGALITY_BY_CREW[request.crew_id] ?? LEGALITY_BY_CREW["C-3310"],
    ),

  cover: (request: CoverRequest) =>
    post<Recommendation>("/api/cover", request, RECOMMENDATION),
};

/* ------------------------------------------------------------------ chat */

export interface ChatCallbacks {
  onEvent: (event: StreamEvent) => void;
  onError?: (error: StreamError) => void;
  onClose?: () => void;
}

/**
 * Opens a turn. Identical signature on both sides of the mock flag, so no
 * component knows which one it is talking to.
 */
export async function chat(
  request: ChatRequest,
  callbacks: ChatCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  if (USE_MOCKS) {
    const reply = pickReply(request.question);
    const threadId = request.thread_id ?? newThreadId();
    const script = scriptFor(
      { ...reply, question: request.question },
      threadId,
    );
    await playScript(script, callbacks.onEvent, signal, MOCK_SPEED);
    callbacks.onClose?.();
    return;
  }
  await streamChat(`${API_BASE}/api/chat`, request, callbacks, { signal });
}

export function newThreadId(): string {
  const random = Math.random().toString(16).slice(2, 6);
  return `T-${random}`;
}

/** Every fixture, for the mock only "sample answers" affordance. */
export const MOCK_REPLIES: Reply[] = REPLIES;
