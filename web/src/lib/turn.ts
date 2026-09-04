/**
 * Turn state, folded from the event stream.
 *
 * One reducer, no answering logic: every field here is copied from an event.
 * The only thing this file decides is ordering and de-duplication, both of
 * which the contract gives it (`seq` is monotonic within a turn).
 *
 * `draft` is the provisional prose. It is never promoted to `reply.text`. The
 * UI shows one or the other, and which one it is showing is visible on screen.
 */

import type {
  Abstention,
  AnswerMode,
  PlanEvent,
  Reply,
  StreamEvent,
  ToolCallEvent,
  ToolResultEvent,
  TraceStep,
  VerificationReport,
} from "@/lib/contracts";

export interface ToolRun {
  call: ToolCallEvent;
  result: ToolResultEvent | null;
}

export type TurnPhase =
  | "opening"
  | "planning"
  | "working"
  | "drafting"
  | "verifying"
  | "settled"
  | "failed";

export interface TurnState {
  localId: string;
  turnId: string | null;
  threadId: string | null;
  question: string;
  mode: AnswerMode | null;
  plan: PlanEvent | null;
  tools: ToolRun[];
  traces: TraceStep[];
  draft: string;
  verifyingAtoms: number | null;
  verification: VerificationReport | null;
  abstention: Abstention | null;
  reply: Reply | null;
  error: { message: string; recoverable: boolean } | null;
  done: boolean;
  totalMs: number | null;
  lastSeq: number;
  startedAt: number;
}

export function emptyTurn(question: string, localId: string): TurnState {
  return {
    localId,
    turnId: null,
    threadId: null,
    question,
    mode: null,
    plan: null,
    tools: [],
    traces: [],
    draft: "",
    verifyingAtoms: null,
    verification: null,
    abstention: null,
    reply: null,
    error: null,
    done: false,
    totalMs: null,
    lastSeq: 0,
    startedAt: Date.now(),
  };
}

export function phaseOf(turn: TurnState): TurnPhase {
  if (turn.error) return "failed";
  if (turn.reply) return "settled";
  if (turn.verification || turn.verifyingAtoms !== null) return "verifying";
  if (turn.draft) return "drafting";
  if (turn.tools.length > 0) return "working";
  if (turn.plan) return "planning";
  return "opening";
}

export function reduceTurn(state: TurnState, event: StreamEvent): TurnState {
  // `seq` is monotonic within a turn, so a repeat is a duplicate delivery.
  if (event.seq <= state.lastSeq && event.type !== "token") return state;
  const next: TurnState = { ...state, lastSeq: event.seq };

  switch (event.type) {
    case "run_started":
      next.turnId = event.turn_id;
      next.threadId = event.thread_id;
      next.question = event.question;
      next.mode = event.mode;
      return next;

    case "plan":
      next.plan = event;
      return next;

    case "tool_call":
      next.tools = [...state.tools, { call: event, result: null }];
      return next;

    case "tool_result": {
      const index = state.tools.findIndex(
        (run) => run.result === null && run.call.tool === event.tool,
      );
      if (index === -1) {
        next.tools = [
          ...state.tools,
          {
            call: {
              type: "tool_call",
              turn_id: event.turn_id,
              seq: event.seq,
              at: event.at,
              tool: event.tool,
              args: event.envelope?.args ?? {},
              label: event.tool.replace(/_/g, " "),
            },
            result: event,
          },
        ];
        return next;
      }
      next.tools = state.tools.map((run, i) =>
        i === index ? { ...run, result: event } : run,
      );
      return next;
    }

    case "trace":
      next.traces = [...state.traces, event.step];
      return next;

    case "token":
      next.draft = state.draft + event.text;
      return next;

    case "verifying":
      next.verifyingAtoms = event.atom_count;
      return next;

    case "verification":
      next.verification = event.report;
      return next;

    case "abstain":
      next.abstention = event.abstention;
      return next;

    case "reply":
      next.reply = event.reply;
      next.threadId = event.reply.thread_id;
      next.verification = event.reply.verification;
      return next;

    case "error":
      next.error = { message: event.message, recoverable: event.recoverable };
      return next;

    case "done":
      next.done = true;
      next.totalMs = event.total_ms;
      return next;

    default:
      return state;
  }
}

/** A short title for the thread rail, taken from the first question. */
export function threadTitle(question: string): string {
  const trimmed = question.trim().replace(/\s+/g, " ");
  return trimmed.length > 48 ? `${trimmed.slice(0, 47)}…` : trimmed;
}
