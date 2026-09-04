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
  RuleUnit,
  QuestionTier,
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

/**
 * Pull the useful body out of a server response.
 *
 * The API wraps collections as `{rules: [...], count}` and tool-backed routes
 * as a full ToolEnvelope carrying `payload` alongside its facts and trace.
 * Both shapes are deliberate: the envelope is what makes a figure on this page
 * traceable to the arithmetic that produced it. The UI wants the body, so the
 * unwrapping happens once, here, rather than in every caller.
 */
function unwrap<T>(body: unknown, key: string): T {
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const record = body as Record<string, unknown>;
    if (key in record) return record[key] as T;
    if ("payload" in record) return record.payload as T;
  }
  return body as T;
}

/**
 * Map server records onto the view types this app renders.
 *
 * The API serves the dataset's own field names (`question_id`, `prompt`) and
 * the memory layer's own (`first_question`, `turns`). Neither is ours to
 * rename: the dataset is read only and the thread store is the agent's. So the
 * translation happens once, here, instead of leaking two vocabularies through
 * every component.
 */
function toSampleQuestion(row: Record<string, unknown>): SampleQuestion {
  return {
    id: String(row.question_id ?? row.id ?? ""),
    tier: (row.tier ?? 1) as QuestionTier,
    question: String(row.prompt ?? row.question ?? ""),
    topic: (row.topic as string | null | undefined) ?? null,
  };
}

/** Which param carries the rule's headline limit, and in what unit. */
const RULE_LIMIT_FIELDS: Record<string, [string, RuleUnit]> = {
  "RULE-FDP-01": ["base_fdp_hours", "hours"],
  "RULE-DUTY-02": ["max_duty_hours", "hours"],
  "RULE-FLT-03": ["max_flight_hours", "hours"],
  "RULE-REST-04": ["min_rest_hours", "hours"],
};

function toRuleDefinition(row: Record<string, unknown>): RuleDefinition {
  // /api/rules returns one envelope per rule, so the rule itself sits under
  // `payload`. The worked example is the most useful thing in it: it is the
  // arithmetic a controller reads when they want to argue with a verdict, so
  // it goes into the card rather than staying buried in the response.
  const body = ((row.payload as Record<string, unknown>) ?? row) ?? {};
  const params = (body.params as Record<string, number>) ?? {};
  const ruleId = String(body.rule_id ?? row.rule_id ?? "");
  const limitField = RULE_LIMIT_FIELDS[ruleId];
  const detail = [body.comparison, body.worked_example]
    .filter((part): part is string => typeof part === "string" && part.length > 0)
    .join("\n\n");

  return {
    rule_id: ruleId as RuleDefinition["rule_id"],
    title: String(body.title ?? ruleId),
    constraint: String(body.text ?? ""),
    limit: limitField ? (params[limitField[0]] ?? null) : null,
    unit: limitField ? limitField[1] : null,
    detail: detail || null,
  };
}

function toWorldSummary(row: Record<string, unknown>): WorldSummary {
  // The server returns the world's own vocabulary (snapshot_utc, hub) with the
  // tallies as flat sibling fields. The ops header wants them as one labelled
  // set it can iterate, so the reshaping happens here rather than in the view.
  const countable = [
    "flights",
    "crew",
    "pairings",
    "pairing_days",
    "reserves",
    "certifications",
    "rules",
  ] as const;
  const counts: Record<string, number> = {};
  for (const key of countable) {
    const value = row[key];
    if (typeof value === "number") counts[key.replace(/_/g, " ")] = value;
  }
  return {
    snapshot: String(row.snapshot_utc ?? row.snapshot ?? ""),
    base: String(row.hub ?? row.base ?? ""),
    date_from: String(row.first_date ?? row.date_from ?? ""),
    date_to: String(row.last_date ?? row.date_to ?? ""),
    counts,
    currency: (row.currency as string | undefined) ?? undefined,
    operator: (row.operator as string | undefined) ?? undefined,
  };
}

function toThreadSummary(row: Record<string, unknown>): ThreadSummary {
  const started = String(row.started_at ?? row.created_at ?? "");
  return {
    thread_id: String(row.thread_id ?? ""),
    title: String(row.first_question ?? row.title ?? "Untitled thread"),
    created_at: started,
    updated_at: String(row.updated_at ?? started),
    turn_count: Number(row.turns ?? row.turn_count ?? 0),
    tier: (row.tier as ThreadSummary["tier"]) ?? null,
  };
}

async function get<T>(path: string, fallback: T, key?: string): Promise<T> {
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
  const body: unknown = await response.json();
  return key ? unwrap<T>(body, key) : (body as T);
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
  return unwrap<T>(await response.json(), "payload");
}

function delay<T>(value: T, ms = 120): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms / MOCK_SPEED));
}

/* ---------------------------------------------------------------- routes */

export const api = {
  health: () => get<HealthResponse>("/api/health", HEALTH),

  worldSummary: async () =>
    USE_MOCKS
      ? WORLD
      : toWorldSummary(
          await get<Record<string, unknown>>(
            "/api/world/summary",
            {},
            "summary",
          ),
        ),

  rules: async () =>
    USE_MOCKS
      ? RULES
      : (
          await get<Record<string, unknown>[]>("/api/rules", [], "rules")
        ).map(toRuleDefinition),

  questions: async () =>
    USE_MOCKS
      ? QUESTIONS
      : (
          await get<Record<string, unknown>[]>(
            "/api/questions",
            [],
            "questions",
          )
        ).map(toSampleQuestion),

  threads: async () =>
    USE_MOCKS
      ? THREADS
      : (
          await get<Record<string, unknown>[]>("/api/threads", [], "threads")
        ).map(toThreadSummary),

  thread: (id: string) =>
    get<ThreadDetail>(`/api/threads/${encodeURIComponent(id)}`, {
      thread_id: id,
      title: THREADS.find((t) => t.thread_id === id)?.title ?? "Thread",
      created_at: THREADS.find((t) => t.thread_id === id)?.created_at ?? "",
      turns: [],
    }),

  brief: (date: string) =>
    get<Watchlist>(`/api/brief?date=${encodeURIComponent(date)}`, WATCHLIST, "payload"),

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
