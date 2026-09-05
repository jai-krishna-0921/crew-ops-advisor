"use client";

/**
 * The live agent trace, built from the reference library's task rows.
 *
 * A controller watches the system decide rather than waiting on a black box:
 * the plan appears before the work, each tool lands as a row with its own
 * status and latency, then the draft streams.
 *
 * The rows are the reference's Task Rows and they are bound to real work: a
 * row's subtitle is the tool's own one-line summary of what it returned, not
 * the word "completed", because the glyph already carries the status and a
 * subtitle that repeats it is a wasted line on the only surface that shows
 * what the agent actually did.
 *
 * The streamed draft is rendered in a visibly provisional state and is never
 * presented as final. That is an honesty requirement from the contract, not a
 * style choice, so the provisional treatment survives `prefers-reduced-motion`
 * as a dotted underline rather than being switched off with the animation.
 */

import {
  BrainIcon,
  ListChecksIcon,
  ShieldCheckIcon,
} from "@phosphor-icons/react/dist/ssr";

import { latency, TOOL_TIER_LABEL, toolLabel } from "@/lib/format";
import { phaseOf, type TurnState } from "@/lib/turn";
import { VerificationBadge } from "@/components/answer/verification";
import {
  ElapsedLoader,
  StreamingText,
  TaskList,
  TaskRow,
  ToolChip,
} from "@/components/ai/elements";
import { Eyebrow, Pill } from "@/components/ui/primitives";

const PHASE_LABEL: Record<string, string> = {
  opening: "Opening the turn",
  planning: "Planning",
  working: "Running tools",
  drafting: "Drafting",
  verifying: "Checking every figure against tool output",
  settled: "Settled",
  failed: "Failed",
};

export function LiveTrace({ turn }: { turn: TurnState }) {
  const phase = phaseOf(turn);
  const running = phase !== "settled" && phase !== "failed";

  return (
    <div className="space-y-3" aria-live="polite" aria-atomic="false">
      {running ? (
        <div className="flex flex-wrap items-center gap-3">
          <ElapsedLoader label={PHASE_LABEL[phase]} since={turn.startedAt} />
          {turn.mode ? (
            <Pill tone="na">{turn.mode === "agent" ? "Agent" : "Deterministic"}</Pill>
          ) : null}
        </div>
      ) : null}

      {turn.plan ? (
        <section aria-label="Plan" className="rounded-md bg-inset/70 px-3.5 py-3">
          <div className="flex items-center gap-1.5">
            <ListChecksIcon size={12} weight="bold" aria-hidden className="text-ink-3" />
            <Eyebrow>Plan</Eyebrow>
            {turn.plan.tier ? (
              <span className="text-xs text-ink-3">
                routed as tier {turn.plan.tier}
              </span>
            ) : null}
          </div>
          <p className="mt-1.5 text-base text-ink">{turn.plan.intent}</p>
          <ol className="mt-2 space-y-1">
            {turn.plan.steps.map((step, index) => (
              <li key={step} className="flex gap-2.5 text-base text-ink-2">
                <span className="num w-3 shrink-0 text-2xs text-ink-3">{index + 1}</span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {/* THE REASONING GOES ABOVE THE TOOL ROWS, and it used to go nowhere.
          `turn.traces` was collected by the reducer and rendered only inside
          the evidence drawer, folded into each tool's envelope, which put the
          thinking underneath the thing it was the reason for. A controller
          reading down this panel met six tool names and then, much later and
          behind a disclosure, the account of why any of them ran.

          Reason first, then the work: that is the order it happened in and
          the order it has to be checked in. */}
      {turn.traces.length > 0 ? (
        <section aria-label="Reasoning" className="rounded-md bg-inset/70 px-3.5 py-3">
          <div className="flex items-center gap-1.5">
            <BrainIcon size={12} weight="bold" aria-hidden className="text-ink-3" />
            <Eyebrow>Reasoning</Eyebrow>
          </div>
          <ol className="mt-2 space-y-1.5">
            {turn.traces.map((step, index) => (
              <li key={`${step.label}-${index}`} className="flex gap-2.5">
                <span className="num w-3 shrink-0 pt-0.5 text-2xs text-ink-3">
                  {index + 1}
                </span>
                <span className="min-w-0 text-base leading-relaxed text-ink-2">
                  <span className="font-medium text-ink">{step.label}.</span>{" "}
                  {step.detail}
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {turn.tools.length > 0 ? (
        <TaskList label="Tool calls">
          {turn.tools.map((run, index) => {
            const settled = run.result !== null;
            const failed = settled && run.result?.ok === false;
            return (
              <TaskRow
                key={`${run.call.tool}-${index}`}
                index={index}
                status={!settled ? "running" : failed ? "failed" : "done"}
                title={toolLabel(run.call.tool)}
                detail={settled ? run.result?.summary : run.call.label}
                meta={
                  settled
                    ? latency(run.result?.latency_ms ?? 0)
                    : TOOL_TIER_LABEL(run.call.tool)
                }
              />
            );
          })}
        </TaskList>
      ) : null}

      {turn.draft ? (
        <section aria-label="Provisional answer" className="space-y-1.5">
          <Eyebrow>Provisional, not yet checked</Eyebrow>
          <StreamingText text={turn.draft} />
        </section>
      ) : null}

      {turn.verifyingAtoms !== null || turn.verification ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md bg-inset/70 px-3 py-2">
          <ShieldCheckIcon size={13} weight="fill" aria-hidden className="text-accent" />
          <span className="text-base text-ink-2">
            {turn.verification
              ? "Grounding check complete"
              : `Checking ${turn.verifyingAtoms} atoms against tool output`}
          </span>
          {turn.verification ? <VerificationBadge report={turn.verification} /> : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * The settled trace, folded down to the chips.
 *
 * Once an answer exists, the interesting question about the work is no longer
 * "what is it doing" but "what did it touch". Six tool chips answer that at a
 * glance and the full rows are one click away.
 */
export function TraceChips({ turn }: { turn: TurnState }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {turn.tools.map((run, index) => (
        <ToolChip
          key={`${run.call.tool}-${index}`}
          tool={run.call.tool}
          ok={run.result?.ok !== false}
          ms={run.result?.latency_ms}
        />
      ))}
    </div>
  );
}

/** Compact summary of a finished trace, shown beside the disclosure. */
export function TraceSummary({ turn }: { turn: TurnState }) {
  const tools = turn.tools.length;
  const ms = turn.totalMs ?? turn.reply?.timings.total_ms ?? 0;
  return (
    <span className="num text-xs text-ink-3">
      {turn.plan ? "planned, " : ""}
      {tools} tool{tools === 1 ? "" : "s"}, {latency(ms)}
    </span>
  );
}
