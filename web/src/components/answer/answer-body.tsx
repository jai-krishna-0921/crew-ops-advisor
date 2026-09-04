"use client";

/**
 * A settled `Reply`, laid out the way a controller reads it.
 *
 * Order is deliberate: the headline is what someone under pressure reads
 * first, then the verified prose, then the structured evidence in descending
 * order of consequence. Caveats sit above the follow-ups, because a limit
 * discovered later is worse than a limit stated up front.
 */

import { WarningIcon } from "@phosphor-icons/react/dist/ssr";

import { useMemo } from "react";

import type { Citation, Reply } from "@/lib/contracts";
import { collectFacts } from "@/lib/fact-link";
import { AbstentionCard } from "@/components/answer/abstention";
import { RecommendationView } from "@/components/answer/cover-options";
import { DataTable } from "@/components/answer/data-table";
import { Markdown } from "@/components/answer/markdown";
import { ImpactReportView } from "@/components/answer/impact-report";
import { RuleTraceCard } from "@/components/answer/rule-trace";
import { SuggestionList } from "@/components/answer/suggestions";
import { VerificationPanel } from "@/components/answer/verification";
import { SourceChip } from "@/components/ai/elements";
import { Disclosure, Eyebrow } from "@/components/ui/primitives";

/** Beyond this many rows, the working is a wall and folds itself away. */
const TRACE_WALL = 8;

/** Beyond this many chips, provenance stops being readable and becomes noise. */
const SOURCE_CAP = 6;

function TraceList({ traces }: { traces: Reply["rule_traces"] }) {
  return (
    <div>
      {traces.map((trace, index) => (
        // Traces from every candidate land in one flat list, so rule id plus
        // date repeats. Keep the index in the key or React omits rows that
        // differ only by which crew member they describe.
        <RuleTraceCard
          key={`${trace.rule_id}-${trace.duty_date ?? "any"}-${index}`}
          trace={trace}
        />
      ))}
    </div>
  );
}

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

  const traces = reply.rule_traces;
  const showTraces = traces.length > 0 && !reply.recommendation;

  // Deduplicated, and capped. A Tier 3 answer touches the same three files
  // forty times, and forty identical chips is not provenance, it is noise.
  const allSources = useMemo(() => {
    const seen = new Map<string, Citation>();
    for (const citation of [
      ...reply.citations,
      ...reply.tool_calls.flatMap((envelope) => envelope.citations),
    ]) {
      seen.set(`${citation.file}::${citation.pointer}`, citation);
    }
    return [...seen.values()];
  }, [reply.citations, reply.tool_calls]);
  const sources = allSources.slice(0, SOURCE_CAP);
  const extraSources = allSources.length - sources.length;

  // WHEN THE TURN ABSTAINS, THE CARD IS THE ANSWER. `headline_of` cuts the
  // first sentence out of `abstention.message` and `Reply.text` carries the
  // rest, so rendering the headline, the text and the card put the same words
  // on the screen three times: a heading, a paragraph under it, and the card's
  // own copy of both. The card is the one that names the reason and offers a
  // way forward, so the card is the one that stays.
  const declined = reply.abstention != null;

  // `_follow_ups` sets `follow_ups` to the abstention's own suggestions, which
  // the card has already rendered. Left alone that is the same three buttons
  // twice, once inside the card and once under it.
  const followUps = declined
    ? reply.follow_ups.filter(
        (question) => !reply.abstention?.suggestions.includes(question),
      )
    : reply.follow_ups;

  return (
    <div className="space-y-4">
      {reply.headline && !declined ? (
        <h2 className="macro max-w-[52ch] text-xl text-ink">{reply.headline}</h2>
      ) : null}

      {reply.text && !declined ? (
        <Markdown text={reply.text} facts={facts} />
      ) : null}

      {reply.abstention ? (
        <AbstentionCard
          abstention={reply.abstention}
          facts={facts}
          onAsk={onAsk}
        />
      ) : null}

      {failed ? <VerificationPanel report={reply.verification} /> : null}

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

      {/* THE WORKING GOES UNDER THE ANSWER, NOT OVER IT. `rule_traces` is
          every trace from every candidate flattened into one list, so a
          ranked recommendation over twenty candidates put roughly two hundred
          rule rows between the headline and the option a controller is
          supposed to act on. Explainability was never the problem; ordering
          was. Each option already carries its own legality report, so when
          there is a recommendation this list is a duplicate and is dropped
          outright. Otherwise it stays, and folds itself away once it is long
          enough to be a wall. */}
      {showTraces ? (
        traces.length > TRACE_WALL ? (
          <Disclosure summary="Every rule evaluated" count={traces.length}>
            <TraceList traces={traces} />
          </Disclosure>
        ) : (
          <section aria-label="Rule traces" className="space-y-1.5">
            <Eyebrow>Rules evaluated</Eyebrow>
            <TraceList traces={traces} />
          </section>
        )
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

      {/* WHERE THE ANSWER CAME FROM, ON THE ANSWER. The citations existed
          only inside the evidence drawer, which means checking a source cost
          a click and a context switch, and nobody reading quickly ever
          discovered they were there at all. Naming the dataset file and the
          record under the answer is the difference between a system that can
          be audited and one that is. */}
      {sources.length > 0 ? (
        <section aria-label="Sources" className="flex flex-wrap items-center gap-1.5">
          <Eyebrow>From</Eyebrow>
          {sources.map((citation) => (
            <SourceChip key={`${citation.file}:${citation.pointer}`} citation={citation} />
          ))}
          {extraSources > 0 ? (
            <span className="text-xs text-ink-3">
              and {extraSources} more, in the evidence panel
            </span>
          ) : null}
        </section>
      ) : null}

      {followUps.length > 0 && onAsk ? (
        <SuggestionList label="Ask next" questions={followUps} onAsk={onAsk} />
      ) : null}
    </div>
  );
}
