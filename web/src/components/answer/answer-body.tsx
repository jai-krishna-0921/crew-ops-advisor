"use client";

/**
 * A settled `Reply`, laid out the way a controller reads it.
 *
 * Order is deliberate: the headline is what someone under pressure reads
 * first, then the verified prose, then the structured evidence in descending
 * order of consequence. Caveats sit above the follow-ups, because a limit
 * discovered later is worse than a limit stated up front.
 */

import { ArrowRightIcon, WarningIcon } from "@phosphor-icons/react/dist/ssr";

import type { Reply } from "@/lib/contracts";
import { collectFacts } from "@/lib/fact-link";
import { latency, MODE_LABEL, MODE_NOTE } from "@/lib/format";
import { AbstentionCard } from "@/components/answer/abstention";
import { RecommendationView } from "@/components/answer/cover-options";
import { DataTable } from "@/components/answer/data-table";
import { GroundedProse } from "@/components/answer/grounded-prose";
import { ImpactReportView } from "@/components/answer/impact-report";
import { RuleTraceCard } from "@/components/answer/rule-trace";
import { VerificationBadge, VerificationPanel } from "@/components/answer/verification";
import { Eyebrow, Pill } from "@/components/ui/primitives";
import { TIER_CHIP } from "@/components/ui/tone";

export function AnswerBody({
  reply,
  onAsk,
}: {
  reply: Reply;
  onAsk?: (question: string) => void;
}) {
  const facts = collectFacts(
    reply.facts,
    ...reply.tool_calls.map((envelope) => envelope.facts),
  );
  const failed = reply.verification.status === "rejected";

  return (
    <div className="space-y-4">
      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          {reply.tier ? (
            <span
              className={`rounded-sm px-1.5 py-0.5 text-2xs font-semibold tracking-wide uppercase ${TIER_CHIP[reply.tier]}`}
            >
              Tier {reply.tier}
            </span>
          ) : null}
          <Pill tone="na" title={MODE_NOTE[reply.mode]}>
            {MODE_LABEL[reply.mode]}
          </Pill>
          <VerificationBadge report={reply.verification} />
          <span className="num text-xs text-ink-3">
            {latency(reply.timings.total_ms)} · {reply.timings.tool_calls} tool
            {reply.timings.tool_calls === 1 ? "" : "s"} · {reply.timings.model_calls}{" "}
            model call{reply.timings.model_calls === 1 ? "" : "s"}
          </span>
        </div>

        {reply.headline ? (
          <h2 className="max-w-[62ch] text-xl leading-snug font-semibold text-ink">
            {reply.headline}
          </h2>
        ) : null}
      </header>

      {reply.text ? <GroundedProse text={reply.text} facts={facts} /> : null}

      {reply.abstention ? (
        <AbstentionCard
          abstention={reply.abstention}
          facts={facts}
          onAsk={onAsk}
        />
      ) : null}

      {failed ? <VerificationPanel report={reply.verification} /> : null}

      {reply.rule_traces.length > 0 ? (
        <section aria-label="Rule traces" className="space-y-1.5">
          <Eyebrow>Rules evaluated</Eyebrow>
          <div className="grid gap-1.5 md:grid-cols-2">
            {reply.rule_traces.map((trace) => (
              <RuleTraceCard
                key={`${trace.rule_id}-${trace.duty_date ?? "any"}`}
                trace={trace}
              />
            ))}
          </div>
        </section>
      ) : null}

      {reply.tables.map((table) => (
        <DataTable key={table.title} table={table} />
      ))}

      {reply.impact && !reply.recommendation ? (
        <ImpactReportView impact={reply.impact} />
      ) : null}

      {reply.recommendation ? (
        <>
          {reply.recommendation.impact ? (
            <ImpactReportView impact={reply.recommendation.impact} />
          ) : null}
          <RecommendationView recommendation={reply.recommendation} />
        </>
      ) : null}

      {reply.caveats.length > 0 ? (
        <section
          aria-label="Caveats"
          className="rounded-md bg-inset px-3 py-2.5 hairline"
        >
          <div className="flex items-center gap-1.5">
            <WarningIcon size={12} weight="fill" aria-hidden className="text-caution" />
            <Eyebrow>Limits of this answer</Eyebrow>
          </div>
          <ul className="mt-1.5 space-y-1">
            {reply.caveats.map((caveat) => (
              <li key={caveat} className="flex gap-2 text-base text-ink-2">
                <span aria-hidden className="mt-2 h-px w-2.5 shrink-0 bg-line-strong" />
                <span className="max-w-[66ch]">{caveat}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {reply.follow_ups.length > 0 && onAsk ? (
        <nav aria-label="Follow up questions" className="flex flex-wrap gap-1.5">
          {reply.follow_ups.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onAsk(question)}
              className="group inline-flex items-center gap-1.5 rounded-sm bg-surface px-2 py-1 text-base text-ink-2 hairline transition-colors duration-100 hover:bg-hover hover:text-ink"
            >
              {question}
              <ArrowRightIcon
                size={11}
                weight="bold"
                aria-hidden
                className="text-ink-3 transition-transform duration-150 group-hover:translate-x-0.5"
              />
            </button>
          ))}
        </nav>
      ) : null}
    </div>
  );
}
