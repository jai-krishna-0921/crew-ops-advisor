/**
 * Turns a `Reply` fixture into the event script the real API would emit.
 *
 * Deriving the script from the reply rather than hand writing twelve event
 * lists keeps the two in step: if a fixture gains a tool call, the timeline
 * gains a chip. The delays are realistic rather than instant, because a UI
 * that only ever sees a fully formed answer never gets its provisional state
 * tested, and the provisional state is the honest part.
 *
 * Ordering follows the contract exactly: `verification` before `reply`,
 * `reply` before `done`, tokens provisional throughout.
 */

import type { Reply, StreamEvent } from "@/lib/contracts";

/** `Omit` over a union has to distribute, or every member loses its fields. */
type DistributiveOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;

type EventDraft = DistributiveOmit<StreamEvent, "seq" | "at">;

export interface ScriptStep {
  /** Milliseconds to wait before emitting, measured from the previous step. */
  after: number;
  event: StreamEvent;
}

interface PlanShape {
  intent: string;
  steps: string[];
  /** Prose the model drafts. Defaults to the settled text. */
  draft?: string;
}

const PLANS: Record<string, PlanShape> = {
  "U-mock-1": {
    intent:
      "Read the reserve register for BLR on the day after the snapshot and attach ratings.",
    steps: [
      "Resolve 'tomorrow' against the snapshot date",
      "List reserves for 2026-09-15 at BLR",
      "Join ratings and reachability from the crew file",
      "Return a table, not prose",
    ],
  },
  "U-mock-2": {
    intent:
      "Read the recorded duty clocks for C-1042 and report headroom under each limit.",
    steps: [
      "Get duty clocks for C-1042",
      "Compare against RULE-DUTY-02 and RULE-FLT-03",
      "Report headroom, not consumption alone",
    ],
  },
  "U-mock-3": {
    intent:
      "Model C-1042 as unavailable on 15 Sep and report what breaks, then what breaks next.",
    steps: [
      "Load the crew record and roster for C-1042",
      "Simulate the absence from 2026-09-15",
      "Check the nearest substitution against all seven rules",
      "Report uncrewed legs, broken pairings and downstream risk",
    ],
  },
  "U-mock-4": {
    intent:
      "Enumerate every way to cover P-2291, check each against all seven rules on every duty day, price the legal ones and rank them.",
    steps: [
      "Load the crew record for C-1042",
      "Expand pairing P-2291 into its duty days and legs",
      "Simulate the absence to size the gap",
      "Find, check, price and rank cover options, keeping the rejects",
    ],
  },
  "U-mock-5": {
    intent:
      "Establish whether the dataset can answer this at all before attempting it.",
    steps: [
      "Read the dataset shape",
      "Look for a weather source among the provided files",
      "Abstain with a reason if there is none",
    ],
  },
  "U-mock-6": {
    intent:
      "Cost cover across every open pairing at BLR for the remainder of the roster week.",
    steps: [
      "Read the dataset shape",
      "Enumerate open pairings for 17 to 20 Sep",
      "Cost cover for each and aggregate",
    ],
    draft:
      "Covering the remaining open pairings would come to roughly INR 2,40,000 in callout and positioning, spread across 11 open pairings between 17 and 20 Sep. The cheapest single fix is P-2291 at INR 18,500.",
  },
};

const DEFAULT_PLAN: PlanShape = {
  intent: "Answer from the dataset, using tools for every figure.",
  steps: ["Resolve the referents", "Call the tools", "Verify every atom"],
};

let clock = 0;

function stamp(): string {
  // Deterministic timestamps so a screenshot is reproducible.
  clock += 1;
  const seconds = String(clock % 60).padStart(2, "0");
  return `2026-09-14T18:00:${seconds}`;
}

/** Splits prose into token sized fragments at word boundaries. */
export function chunkTokens(text: string): string[] {
  const out: string[] = [];
  const words = text.split(/(\s+)/);
  let buffer = "";
  for (const word of words) {
    buffer += word;
    if (buffer.trim().length >= 9 || /\n/.test(word)) {
      out.push(buffer);
      buffer = "";
    }
  }
  if (buffer) out.push(buffer);
  return out;
}

export function scriptFor(reply: Reply, threadId: string): ScriptStep[] {
  clock = 0;
  const plan = PLANS[reply.turn_id] ?? DEFAULT_PLAN;
  const steps: ScriptStep[] = [];
  let seq = 0;
  const base = { turn_id: reply.turn_id };

  const push = (after: number, event: EventDraft) => {
    seq += 1;
    steps.push({
      after,
      event: { ...event, seq, at: stamp() } as StreamEvent,
    });
  };

  push(0, {
    ...base,
    type: "run_started",
    thread_id: threadId,
    question: reply.question,
    mode: reply.mode,
  });

  push(340, {
    ...base,
    type: "plan",
    intent: plan.intent,
    tier: reply.tier ?? null,
    steps: plan.steps,
  });

  for (const envelope of reply.tool_calls) {
    push(210, {
      ...base,
      type: "tool_call",
      tool: envelope.tool,
      args: envelope.args,
      label: labelFor(envelope.tool, envelope.args),
    });
    push(Math.max(160, Math.round(envelope.latency_ms * 0.9)), {
      ...base,
      type: "tool_result",
      tool: envelope.tool,
      ok: envelope.ok,
      latency_ms: envelope.latency_ms,
      summary: summaryFor(envelope.payload),
      envelope,
    });
  }

  for (const step of reply.traces) {
    push(120, { ...base, type: "trace", step });
  }

  const draft = plan.draft ?? reply.text;
  for (const text of chunkTokens(draft)) {
    push(34, { ...base, type: "token", text });
  }

  push(260, {
    ...base,
    type: "verifying",
    atom_count: reply.verification.checked_atoms,
  });

  push(420, { ...base, type: "verification", report: reply.verification });

  if (reply.kind === "abstain" && reply.abstention) {
    push(200, { ...base, type: "abstain", abstention: reply.abstention });
  }

  push(180, {
    ...base,
    type: "reply",
    reply: { ...reply, thread_id: threadId },
  });

  push(60, { ...base, type: "done", total_ms: reply.timings.total_ms });

  return steps;
}

function labelFor(tool: string, args: Record<string, unknown>): string {
  const crew = typeof args.crew_id === "string" ? args.crew_id : null;
  const pairing = typeof args.pairing_id === "string" ? args.pairing_id : null;
  const base = typeof args.base === "string" ? args.base : null;
  switch (tool) {
    case "get_crew_detail":
      return `Reading the crew record for ${crew}`;
    case "get_duty_clocks":
      return `Checking duty clocks for ${crew}`;
    case "list_reserves":
      return `Listing reserves at ${base ?? "base"}`;
    case "get_pairing":
      return `Expanding pairing ${pairing}`;
    case "simulate_absence":
      return `Modelling ${crew} as unavailable`;
    case "check_legality":
      return `Checking ${crew} against all seven rules`;
    case "find_cover_options":
      return `Searching cover for ${pairing}`;
    case "get_world_summary":
      return "Reading the dataset shape";
    default:
      return tool.replace(/_/g, " ");
  }
}

function summaryFor(payload: unknown): string {
  if (
    payload &&
    typeof payload === "object" &&
    "note" in payload &&
    typeof (payload as { note: unknown }).note === "string"
  ) {
    return (payload as { note: string }).note;
  }
  return "Result returned";
}

/**
 * Plays a script through a callback, honouring an abort signal. Returns a
 * promise that settles when the script finishes or is aborted.
 */
export function playScript(
  script: ScriptStep[],
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  speed = 1,
): Promise<void> {
  return new Promise((resolve) => {
    let index = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const stop = () => {
      if (timer) clearTimeout(timer);
      signal?.removeEventListener("abort", stop);
      resolve();
    };

    const tick = () => {
      if (signal?.aborted) return stop();
      if (index >= script.length) return stop();
      const step = script[index];
      index += 1;
      onEvent(step.event);
      const next = script[index];
      timer = setTimeout(tick, next ? next.after / speed : 0);
    };

    signal?.addEventListener("abort", stop);
    timer = setTimeout(tick, script[0]?.after ?? 0);
  });
}
