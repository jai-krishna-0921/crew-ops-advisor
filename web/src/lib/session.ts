/**
 * Session persistence, and the seam where contextual memory will attach.
 *
 * Two different things are stored, and they are kept apart on purpose.
 *
 * **Session** is this browser tab's working state: which thread is open and
 * what has been said in it. It survives a reload so a controller who
 * accidentally refreshes mid-disruption does not lose the thread they were
 * reading. It lives in `sessionStorage`, so a new tab starts clean.
 *
 * **Memory** is what the assistant should carry between turns: the crew and
 * pairings this conversation is about, and anything the controller has pinned.
 * Today it is derived locally and stored per thread. It is a stub, and it is
 * marked as one, because the real store belongs on the server beside the
 * LangGraph checkpointer: memory that lives only in one browser is not memory
 * a second controller taking over the desk can rely on.
 *
 * Every read is defensive. Storage throws in private windows and can return
 * anything at all after a schema change, so a bad value degrades to a clean
 * session rather than a broken page.
 */

import type { ConversationState } from "@/lib/conversation";
import { EMPTY_CONVERSATION } from "@/lib/conversation";

const SESSION_KEY = "crewops.session.v1";
const MEMORY_PREFIX = "crewops.memory.v1.";

/** Bumped when the stored shape changes, so old payloads are discarded. */
const SCHEMA = 1;

interface StoredSession {
  schema: number;
  threadId: string | null;
  /** Only settled turns are stored. A half-streamed turn is not worth reviving. */
  turns: ConversationState["turns"];
  savedAt: number;
}

function safeGet(storage: Storage | undefined, key: string): string | null {
  try {
    return storage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

function safeSet(storage: Storage | undefined, key: string, value: string): void {
  try {
    storage?.setItem(key, value);
  } catch {
    // Private mode, quota, or blocked site data. Losing persistence is a
    // degraded session, not a broken one.
  }
}

function session(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  return window.sessionStorage;
}

function local(): Storage | undefined {
  if (typeof window === "undefined") return undefined;
  return window.localStorage;
}

export function saveSession(state: ConversationState): void {
  // A turn still streaming has no reply and would restore as a dead spinner.
  const settled = state.turns.filter((turn) => turn.reply !== null);
  if (settled.length === 0 && state.threadId === null) {
    clearSession();
    return;
  }
  const payload: StoredSession = {
    schema: SCHEMA,
    threadId: state.threadId,
    turns: settled,
    savedAt: Date.now(),
  };
  safeSet(session(), SESSION_KEY, JSON.stringify(payload));
}

export function loadSession(): ConversationState {
  const raw = safeGet(session(), SESSION_KEY);
  if (!raw) return EMPTY_CONVERSATION;
  try {
    const parsed = JSON.parse(raw) as Partial<StoredSession>;
    if (parsed.schema !== SCHEMA || !Array.isArray(parsed.turns)) {
      return EMPTY_CONVERSATION;
    }
    return {
      threadId: typeof parsed.threadId === "string" ? parsed.threadId : null,
      turns: parsed.turns,
      status: "idle",
      loadError: null,
    };
  } catch {
    return EMPTY_CONVERSATION;
  }
}

export function clearSession(): void {
  try {
    session()?.removeItem(SESSION_KEY);
  } catch {
    // Nothing to do. The next save overwrites it anyway.
  }
}

/* ------------------------------------------------------- contextual memory */

/**
 * What a conversation is about, carried between turns.
 *
 * STUB. Derived in the browser and stored per thread. The server owns the real
 * article: `crewops.agent.memory` already checkpoints thread state, and this
 * shape is what a `GET /api/threads/{id}/memory` route would return. Wiring it
 * up is a change to `loadMemory` and `saveMemory` and nothing else.
 */
export interface ThreadMemory {
  threadId: string;
  /** Crew, pairings and flights this conversation has touched, most recent first. */
  entities: MemoryEntity[];
  /** Facts the controller explicitly kept. Survives the whole thread. */
  pinned: string[];
  /** The snapshot every answer in this thread was resolved against. */
  asOf: string | null;
  updatedAt: number;
}

export interface MemoryEntity {
  kind: "crew" | "pairing" | "flight" | "station" | "rule";
  id: string;
  /** How many turns in this thread have referred to it. */
  mentions: number;
}

const ENTITY_PATTERNS: ReadonlyArray<[MemoryEntity["kind"], RegExp]> = [
  ["crew", /\bC-\d{3,4}\b/g],
  ["pairing", /\bP-\d{3,4}\b/g],
  ["flight", /\bDX\d{3}\b/g],
  ["rule", /\bRULE-[A-Z]+-\d{2}\b/g],
];

export function emptyMemory(threadId: string): ThreadMemory {
  return { threadId, entities: [], pinned: [], asOf: null, updatedAt: Date.now() };
}

/**
 * Fold one exchange into a thread's memory.
 *
 * Entity extraction only. It does not attempt to summarise, because a summary
 * the controller cannot check is exactly the kind of ungrounded content this
 * system refuses to produce elsewhere.
 */
export function rememberTurn(
  memory: ThreadMemory,
  question: string,
  answer: string,
): ThreadMemory {
  const counts = new Map<string, MemoryEntity>();
  for (const entity of memory.entities) counts.set(`${entity.kind}:${entity.id}`, { ...entity });

  const haystack = `${question}\n${answer}`;
  for (const [kind, pattern] of ENTITY_PATTERNS) {
    for (const match of haystack.matchAll(pattern)) {
      const key = `${kind}:${match[0]}`;
      const existing = counts.get(key);
      if (existing) existing.mentions += 1;
      else counts.set(key, { kind, id: match[0], mentions: 1 });
    }
  }

  return {
    ...memory,
    entities: [...counts.values()].sort((a, b) => b.mentions - a.mentions).slice(0, 24),
    updatedAt: Date.now(),
  };
}

export function loadMemory(threadId: string): ThreadMemory {
  const raw = safeGet(local(), MEMORY_PREFIX + threadId);
  if (!raw) return emptyMemory(threadId);
  try {
    const parsed = JSON.parse(raw) as Partial<ThreadMemory>;
    if (!Array.isArray(parsed.entities)) return emptyMemory(threadId);
    return {
      threadId,
      entities: parsed.entities,
      pinned: Array.isArray(parsed.pinned) ? parsed.pinned : [],
      asOf: typeof parsed.asOf === "string" ? parsed.asOf : null,
      updatedAt: typeof parsed.updatedAt === "number" ? parsed.updatedAt : Date.now(),
    };
  } catch {
    return emptyMemory(threadId);
  }
}

export function saveMemory(memory: ThreadMemory): void {
  safeSet(local(), MEMORY_PREFIX + memory.threadId, JSON.stringify(memory));
}
