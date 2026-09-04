"use client";

/**
 * The evidence drawer.
 *
 * Three views over one turn: every citable fact, the tool calls that produced
 * them with their latencies and raw envelopes, and the dataset records that
 * were touched. Nothing here is summarised: this is the audit trail, and a
 * summarised audit trail is not one.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import {
  CheckCircleIcon,
  ClockIcon,
  DatabaseIcon,
  FunctionIcon,
  QuestionIcon,
  XCircleIcon,
  XIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { Citation, Fact, Provenance } from "@/lib/contracts";
import {
  factValue,
  latency,
  PROVENANCE_LABEL,
  PROVENANCE_NOTE,
  TOOL_TIER_LABEL,
} from "@/lib/format";
import type { ToolRun } from "@/lib/turn";
import { useFacts } from "@/components/evidence/fact-context";
import {
  Disclosure,
  EmptyState,
  Eyebrow,
  IconButton,
  Pill,
  Segmented,
  Token,
} from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

type View = "facts" | "tools" | "sources";
type ProvFilter = "all" | Provenance;

const PROV_ICON: Record<Provenance, typeof DatabaseIcon> = {
  dataset: DatabaseIcon,
  computed: FunctionIcon,
  assumed: QuestionIcon,
};

const PROV_TEXT: Record<Provenance, string> = {
  dataset: "text-ink-2",
  computed: "text-accent",
  assumed: "text-caution",
};

export function EvidenceDrawer({
  facts,
  tools,
  citations,
  onClose,
}: {
  facts: Fact[];
  tools: ToolRun[];
  citations: Citation[];
  onClose: () => void;
}) {
  const [view, setView] = useState<View>("facts");
  const [filter, setFilter] = useState<ProvFilter>("all");

  const counts = useMemo(() => {
    const by: Record<Provenance, number> = { dataset: 0, computed: 0, assumed: 0 };
    for (const fact of facts) by[fact.provenance] += 1;
    return by;
  }, [facts]);

  const visible = useMemo(
    () => (filter === "all" ? facts : facts.filter((f) => f.provenance === filter)),
    [facts, filter],
  );

  return (
    <aside
      aria-label="Evidence"
      className="flex h-full min-h-0 w-full flex-col bg-canvas"
    >
      <header className="flex items-center gap-2 px-3 py-2">
        <h2 className="text-base font-semibold text-ink">Evidence</h2>
        <span className="num text-xs text-ink-3">
          {facts.length} facts · {tools.length} tool calls
        </span>
        <div className="ml-auto">
          <IconButton label="Close evidence" onClick={onClose}>
            <XIcon size={17} weight="bold" aria-hidden />
          </IconButton>
        </div>
      </header>

      <div className="px-3 py-2">
        <Segmented
          label="Evidence view"
          value={view}
          onChange={setView}
          options={[
            { value: "facts", label: "Facts", count: facts.length },
            { value: "tools", label: "Tools", count: tools.length },
            { value: "sources", label: "Sources", count: citations.length },
          ]}
        />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {view === "facts" ? (
          <>
            <div className="sticky top-0 z-10 bg-canvas px-3 py-2">
              <Segmented
                label="Filter by provenance"
                value={filter}
                onChange={setFilter}
                options={[
                  { value: "all", label: "All" },
                  { value: "dataset", label: "Dataset", count: counts.dataset },
                  { value: "computed", label: "Computed", count: counts.computed },
                  { value: "assumed", label: "Assumed", count: counts.assumed },
                ]}
              />
            </div>
            {visible.length === 0 ? (
              <div className="p-3">
                <EmptyState
                  title="No facts yet"
                  detail="Facts appear here as the tools return them. Every figure in the answer will be one of these."
                />
              </div>
            ) : (
              <ul className="rules mx-3 mb-3">
                {visible.map((fact) => (
                  <FactRow key={fact.key} fact={fact} />
                ))}
              </ul>
            )}
          </>
        ) : null}

        {view === "tools" ? (
          <ToolTimeline tools={tools} />
        ) : null}

        {view === "sources" ? (
          <CitationList citations={citations} />
        ) : null}
      </div>
    </aside>
  );
}

/* -------------------------------------------------------------- fact row */

function FactRow({ fact }: { fact: Fact }) {
  const { active, pinned, setActive, pin } = useFacts();
  const lit = active === fact.key || pinned === fact.key;
  const ref = useRef<HTMLLIElement>(null);
  const Icon = PROV_ICON[fact.provenance];

  useEffect(() => {
    if (pinned === fact.key && ref.current) {
      ref.current.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [pinned, fact.key]);

  return (
    <li
      ref={ref}
      onMouseEnter={() => setActive(fact.key)}
      onMouseLeave={() => setActive(null)}
      className={cx(
        "px-3 py-2 transition-colors duration-100",
        lit ? "bg-accent-tint" : "hover:bg-hover",
      )}
    >
      <button
        type="button"
        onClick={() => pin(fact.key)}
        aria-pressed={pinned === fact.key}
        className="w-full min-w-0 cursor-pointer text-left"
      >
        {/* `shrink-0` on the value was right for a number and wrong for the
            text facts: a rule's full sentence arrives as a Fact too, and an
            unshrinkable span holding forty words pushed the row 155px past
            the panel it lives in. The value wraps now, and the label gives way
            first, because a truncated label is still recognisable and a
            truncated value is a different value. */}
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="min-w-0 flex-1 truncate text-base font-medium text-ink">
            {fact.label}
          </span>
          <span className="num max-w-full min-w-0 break-words text-base text-ink">
            {factValue(fact.value, fact.unit)}
          </span>
        </div>

        <div className="mt-1 flex min-w-0 items-center gap-1.5">
          <Icon
            size={11}
            weight="bold"
            aria-hidden
            className={PROV_TEXT[fact.provenance]}
          />
          <span
            className={cx("label-micro", PROV_TEXT[fact.provenance])}
            title={PROVENANCE_NOTE[fact.provenance]}
          >
            {PROVENANCE_LABEL[fact.provenance]}
          </span>
          <span
            className="mono min-w-0 truncate text-2xs text-ink-3"
            title={fact.key}
          >
            {fact.key}
          </span>
        </div>

        {/* `break-words` because a derivation is one long expression with
            no space the browser is willing to break at, and truncating it
            would hide the arithmetic that is the entire reason the row is
            here. */}
        {fact.derivation ? (
          <p className="mono mt-1.5 rounded-sm bg-inset p-2 text-xs leading-relaxed break-words text-ink-2">
            {fact.derivation}
          </p>
        ) : null}

        <p className="mono mt-1 truncate text-2xs text-ink-3" title={fact.source}>
          {fact.source}
        </p>
      </button>
    </li>
  );
}

/* --------------------------------------------------------- tool timeline */

export function ToolTimeline({ tools }: { tools: ToolRun[] }) {
  if (tools.length === 0) {
    return (
      <div className="p-3">
        <EmptyState
          title="No tool calls yet"
          detail="Each call the agent makes appears here with its arguments, latency and full result envelope."
        />
      </div>
    );
  }

  return (
    <ol className="rules m-3">
      {tools.map((run, index) => {
        const ok = run.result?.ok ?? null;
        const envelope = run.result?.envelope ?? null;
        return (
          <li key={`${run.call.tool}-${index}`} className="px-3 py-2.5">
            <div className="flex items-center gap-2">
              <span className="num w-4 shrink-0 text-2xs text-ink-3">
                {index + 1}
              </span>
              {ok === null ? (
                <ClockIcon
                  size={13}
                  weight="bold"
                  aria-hidden
                  className="anim-spin shrink-0 text-accent"
                />
              ) : ok ? (
                <CheckCircleIcon
                  size={13}
                  weight="fill"
                  aria-hidden
                  className="shrink-0 text-pass"
                />
              ) : (
                <XCircleIcon
                  size={13}
                  weight="fill"
                  aria-hidden
                  className="shrink-0 text-breach"
                />
              )}
              <Token>{run.call.tool}</Token>
              <Pill tone="na">{TOOL_TIER_LABEL(run.call.tool)}</Pill>
              {run.result ? (
                <span className="num ml-auto text-xs text-ink-3">
                  {latency(run.result.latency_ms)}
                </span>
              ) : (
                <span className="ml-auto text-xs text-ink-3">running</span>
              )}
            </div>

            <p className="mt-1 pl-6 text-base text-ink-2">{run.call.label}</p>
            {run.result ? (
              <p className="mt-0.5 pl-6 text-xs text-ink-3">{run.result.summary}</p>
            ) : null}

            {envelope ? (
              <div className="mt-1.5 pl-5">
                <Disclosure summary="Envelope" count={envelope.facts.length}>
                  <div className="space-y-2 px-1 pb-1">
                    {envelope.trace.length > 0 ? (
                      <div>
                        <Eyebrow>Trace</Eyebrow>
                        <ul className="mt-1 space-y-1">
                          {envelope.trace.map((step, i) => (
                            <li key={i} className="text-xs text-ink-2">
                              <span className="font-medium text-ink">
                                {step.label}.
                              </span>{" "}
                              {step.detail}
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <div>
                      <Eyebrow>Raw</Eyebrow>
                      <pre className="mt-1 max-h-64 overflow-auto rounded-sm bg-inset p-2 text-2xs leading-relaxed text-ink-2">
                        {JSON.stringify(
                          {
                            tool: envelope.tool,
                            args: envelope.args,
                            ok: envelope.ok,
                            latency_ms: envelope.latency_ms,
                            facts: envelope.facts.length,
                            citations: envelope.citations,
                            payload: envelope.payload,
                          },
                          null,
                          2,
                        )}
                      </pre>
                    </div>
                  </div>
                </Disclosure>
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------- citations */

function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return (
      <div className="p-3">
        <EmptyState
          title="No sources yet"
          detail="Every dataset file and record the tools touched is listed here."
        />
      </div>
    );
  }
  return (
    <ul className="rules m-3">
      {citations.map((citation, index) => (
        <li key={`${citation.file}-${index}`} className="px-3 py-2">
          <p className="num text-base text-ink">{citation.file}</p>
          <p className="num mt-0.5 text-xs text-ink-2">{citation.pointer}</p>
          {citation.note ? (
            <p className="mt-0.5 text-xs text-ink-3">{citation.note}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

