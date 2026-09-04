"use client";

/**
 * The live agent trace.
 *
 * A controller watches the system decide rather than waiting on a black box:
 * the plan appears before the work, tool chips resolve one at a time with
 * their latency, then the draft streams.
 *
 * The streamed draft is rendered in a visibly provisional state and is never
 * presented as final. That is an honesty requirement from the contract, not a
 * style choice, so the provisional treatment survives `prefers-reduced-motion`
 * as a dotted underline rather than being switched off with the animation.
 */

import {
  CheckCircleIcon,
  CircleDashedIcon,
  ListChecksIcon,
  ShieldCheckIcon,
} from "@phosphor-icons/react/dist/ssr";

import { latency, TOOL_TIER_LABEL } from "@/lib/format";
import { phaseOf, type TurnState } from "@/lib/turn";
import { VerificationBadge } from "@/components/answer/verification";
import { Eyebrow, Pill, Token } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

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

  return (
    <div className="space-y-3" aria-live="polite" aria-atomic="false">
      <div className="flex items-center gap-2">
        <CircleDashedIcon
          size={13}
          weight="bold"
          aria-hidden
          className="anim-spin text-accent"
        />
        <span className="text-base text-ink-2">{PHASE_LABEL[phase]}</span>
        {turn.mode ? (
          <Pill tone="na">{turn.mode === "agent" ? "Agent" : "Deterministic"}</Pill>
        ) : null}
      </div>

      {turn.plan ? (
        <section
          aria-label="Plan"
          className="rounded-md bg-surface px-3 py-2.5 hairline"
        >
          <div className="flex items-center gap-1.5">
            <ListChecksIcon size={12} weight="bold" aria-hidden className="text-ink-3" />
            <Eyebrow>Plan</Eyebrow>
            {turn.plan.tier ? <Pill tone="accent">Tier {turn.plan.tier}</Pill> : null}
          </div>
          <p className="mt-1.5 max-w-[68ch] text-base text-ink">{turn.plan.intent}</p>
          <ol className="mt-2 space-y-1">
            {turn.plan.steps.map((step, index) => (
              <li key={step} className="flex gap-2 text-base text-ink-2">
                <span className="num w-4 shrink-0 text-2xs text-ink-3">
                  {index + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {turn.tools.length > 0 ? (
        <ul aria-label="Tool calls" className="space-y-1">
          {turn.tools.map((run, index) => {
            const settled = run.result !== null;
            return (
              <li
                key={`${run.call.tool}-${index}`}
                className={cx(
                  "anim-fade-up flex flex-wrap items-center gap-2 rounded-sm bg-surface px-2.5 py-1.5 hairline",
                  !settled && "anim-pulse-ring",
                )}
              >
                {settled ? (
                  <CheckCircleIcon
                    size={13}
                    weight="fill"
                    aria-hidden
                    className={run.result?.ok ? "text-pass" : "text-breach"}
                  />
                ) : (
                  <CircleDashedIcon
                    size={13}
                    weight="bold"
                    aria-hidden
                    className="anim-spin text-accent"
                  />
                )}
                <Token>{run.call.tool}</Token>
                <Pill tone="na">{TOOL_TIER_LABEL(run.call.tool)}</Pill>
                <span className="min-w-0 flex-1 truncate text-base text-ink-2">
                  {settled ? run.result?.summary : run.call.label}
                </span>
                <span className="num shrink-0 text-xs text-ink-3">
                  {settled ? latency(run.result?.latency_ms ?? 0) : "running"}
                </span>
              </li>
            );
          })}
        </ul>
      ) : null}

      {turn.draft ? (
        <section aria-label="Provisional answer" className="space-y-1.5">
          <div className="flex items-center gap-1.5">
            <Eyebrow>Provisional, not yet checked</Eyebrow>
          </div>
          <div className="max-w-[68ch] space-y-2 text-md leading-relaxed">
            {turn.draft.split(/\n{2,}/).map((paragraph, index) => (
              <p key={index} className="provisional">
                {paragraph}
              </p>
            ))}
          </div>
        </section>
      ) : null}

      {turn.verifyingAtoms !== null || turn.verification ? (
        <div className="flex flex-wrap items-center gap-2 rounded-sm bg-surface px-2.5 py-1.5 hairline">
          <ShieldCheckIcon size={13} weight="fill" aria-hidden className="text-accent" />
          <span className="text-base text-ink-2">
            {turn.verification
              ? "Grounding check complete"
              : `Checking ${turn.verifyingAtoms} atoms against tool output`}
          </span>
          {turn.verification ? (
            <VerificationBadge report={turn.verification} />
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Compact summary of a finished trace, shown above a settled answer. */
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
