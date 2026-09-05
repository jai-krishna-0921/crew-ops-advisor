"use client";

/**
 * The AI interface primitives, from the reference library, bound to this
 * product's data rather than to a demo payload.
 *
 * Each of these exists in the reference set as a generic component: a task
 * row that shows an agent doing something, a context card that shows a
 * retrieved chunk, a recommendation card with a confidence meter. Taking them
 * as-is would give a chat that looks like an agent demo. What makes them
 * carry weight here is what gets bound into them: a task row's subtitle is
 * the tool's own summary of what it returned, a context card's body is the
 * derivation string a computed Fact is required to carry, and the confidence
 * meter reads a field the ranking engine set.
 *
 * The rule the whole submission turns on applies here too. Nothing in this
 * file computes anything. Every figure on screen was put there by a tool.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  CaretRightIcon,
  CheckIcon,
  CircleNotchIcon,
  DatabaseIcon,
  FunctionIcon,
  QuotesIcon,
  SparkleIcon,
  WarningIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { Citation, Confidence, Fact } from "@/lib/contracts";
import { factValue, latency, PROVENANCE_LABEL, toolLabel } from "@/lib/format";
import { cx } from "@/components/ui/tone";

/* ====================================================== 1. loading state */

/**
 * The pixel-grid loader, with the elapsed clock the reference pairs it with.
 *
 * The elapsed seconds are the point. A spinner says "something is happening";
 * a spinner with 4s next to it says "this is a search, not a hang", which is
 * the only question anybody actually has while waiting. It counts from mount
 * and stops when the caller unmounts it.
 */
export function ElapsedLoader({
  label,
  since,
}: {
  label: string;
  since: number;
}) {
  // Keep the first render identical on the server and browser. Reading the
  // clock in the state initializer makes the elapsed label differ during
  // hydration, which React cannot patch safely.
  const [now, setNow] = useState(0);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initialise a client-only clock after hydration
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(id);
  }, []);

  const seconds = Math.max(0, (now - since) / 1000);

  return (
    <div className="flex items-center gap-2.5">
      <PixelGrid />
      <span className="text-base text-ink-2">{label}</span>
      <span
        className="num text-xs text-ink-3 tabular-nums"
        aria-label={`${seconds.toFixed(0)} seconds elapsed`}
      >
        {seconds.toFixed(1)}s
      </span>
    </div>
  );
}

/** Nine cells lighting in a fixed order. Opacity only, so it costs nothing. */
function PixelGrid() {
  return (
    <span aria-hidden className="grid shrink-0 grid-cols-3 gap-[2px]">
      {[0, 5, 2, 7, 1, 6, 3, 8, 4].map((step, index) => (
        <span
          key={index}
          className="block size-[3px] rounded-[1px] bg-accent"
          style={{
            animation: "co-settle 1.1s var(--ease) infinite alternate",
            animationDelay: `${step * 90}ms`,
          }}
        />
      ))}
    </span>
  );
}

/* ========================================================== 2. task rows */

export type TaskStatus = "running" | "done" | "failed";

/**
 * One unit of work the agent did, as a row rather than as a card.
 *
 * The reference draws these as a list with a status glyph, a title, a
 * subtitle and a right-aligned duration, and that shape is right because a
 * controller reads down the glyph column to find the one that failed. The
 * only liberty taken is that the subtitle is never a status word: "running",
 * "completed" is already in the glyph, so the subtitle carries what the tool
 * actually said it found.
 */
export function TaskRow({
  status,
  title,
  detail,
  meta,
  tone,
  index = 0,
}: {
  status: TaskStatus;
  title: ReactNode;
  detail?: ReactNode;
  meta?: ReactNode;
  tone?: "accent" | "breach";
  index?: number;
}) {
  return (
    <li
      className="anim-stagger flex items-center gap-2.5 px-3 py-2"
      style={{ "--i": index } as React.CSSProperties}
    >
      <StatusGlyph status={status} tone={tone} />
      <span className="min-w-0 shrink-0 text-base font-medium text-ink">{title}</span>
      {detail ? (
        <span className="min-w-0 flex-1 truncate text-base text-ink-2">{detail}</span>
      ) : (
        <span className="flex-1" />
      )}
      {meta ? <span className="num shrink-0 text-xs text-ink-3">{meta}</span> : null}
    </li>
  );
}

function StatusGlyph({
  status,
  tone,
}: {
  status: TaskStatus;
  tone?: "accent" | "breach";
}) {
  if (status === "running") {
    return (
      <CircleNotchIcon
        size={13}
        weight="bold"
        aria-label="running"
        className="anim-spin shrink-0 text-accent"
      />
    );
  }
  if (status === "failed") {
    return (
      <WarningIcon
        size={13}
        weight="fill"
        aria-label="failed"
        className="shrink-0 text-breach"
      />
    );
  }
  return (
    <CheckIcon
      size={13}
      weight="bold"
      aria-label="completed"
      className={cx("shrink-0", tone === "breach" ? "text-breach" : "text-pass")}
    />
  );
}

/** The list the rows live in. Divisions are grid gaps, never borders. */
export function TaskList({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <ul aria-label={label} className="rules text-base">
      {children}
    </ul>
  );
}

/* ========================================================= 3. tool chips */

/**
 * A tool call at its most compact: the name, and whether it came back.
 *
 * Used where the trace is closed and only the shape of the work is on show.
 * The tool name is monospace here and almost nowhere else, because this is a
 * function a machine ran and the register change is information.
 */
export function ToolChip({
  tool,
  ok,
  ms,
}: {
  tool: string;
  ok: boolean;
  ms?: number | null;
}) {
  return (
    <span
      title={`${toolLabel(tool)}${ms ? `, ${latency(ms)}` : ""}`}
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full bg-inset px-2 py-0.5 text-2xs",
        ok ? "text-ink-2" : "text-breach",
      )}
    >
      <FunctionIcon size={10} weight="bold" aria-hidden className="text-ink-3" />
      <span className="mono">{tool}</span>
      {ms ? <span className="num text-ink-3">{latency(ms)}</span> : null}
    </span>
  );
}

/* =========================================================== 4. thinking */

/**
 * The expandable reasoning trace.
 *
 * Closed by default and closed once the answer settles, because the finished
 * answer is what a controller under pressure wants first. Open, it is the
 * whole argument: the plan, then the steps, in the order they ran.
 *
 * The summary line stays honest about what it is hiding. "How this was worked
 * out, 6 steps" is a claim the row underneath has to be able to support.
 *
 * `brand-edge` and a rotating caret, not a grey box with a "Show"/"Hide"
 * label: that combination is the product's own disclosure idiom (see
 * `Disclosure` in `ui/primitives.tsx`), used here instead of the plain
 * collapsible box every chat product ships this exact feature as.
 */
export function Thinking({
  summary,
  meta,
  defaultOpen = false,
  children,
}: {
  summary: string;
  meta?: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-md pl-3.5 brand-edge">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 rounded-r-md px-3 py-2 text-left hover:bg-hover"
      >
        <SparkleIcon
          size={12}
          weight="fill"
          aria-hidden
          className="shrink-0"
          style={{ color: "var(--brand-from)" }}
        />
        <span className="text-base font-medium text-ink-2">{summary}</span>
        {meta ? <span className="num text-xs text-ink-3">{meta}</span> : null}
        <CaretRightIcon
          size={12}
          weight="bold"
          aria-hidden
          className={cx(
            "ml-auto shrink-0 text-ink-3 transition-transform duration-200 ease-out-quint",
            open && "rotate-90",
          )}
        />
      </button>
      {open ? <div className="anim-fade-up px-3 pb-3">{children}</div> : null}
    </div>
  );
}

/* ==================================================== 5. streaming text */

/**
 * Streamed prose, drawn as provisional for as long as it is provisional.
 *
 * The caret is not decoration. Until the `reply` event lands, none of this
 * text has been through the grounding check, and the interface has to say so
 * rather than let a draft figure look like a verified one. `.provisional`
 * carries a dim plus a travelling sheen, and it degrades to a dotted
 * underline under `prefers-reduced-motion` rather than switching off: the
 * honesty signal is not an animation preference.
 */
export function StreamingText({ text }: { text: string }) {
  const paragraphs = text.split(/\n{2,}/);
  return (
    <div className="space-y-2 text-md leading-relaxed">
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="provisional">
          {paragraph}
          {index === paragraphs.length - 1 ? <Caret /> : null}
        </p>
      ))}
    </div>
  );
}

function Caret() {
  return (
    <span
      aria-hidden
      className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[0.15em] bg-accent"
      style={{ animation: "co-settle 900ms steps(2, end) infinite alternate" }}
    />
  );
}

/* ================================================== 6. confidence meter */

const CONFIDENCE_STEPS: Record<Confidence, number> = { low: 1, medium: 2, high: 3 };

const CONFIDENCE_NOTE: Record<Confidence, string> = {
  high: "Every rule resolved on real data, on every day of the cover.",
  medium: "Legal, but something in the ranking rests on an assumption.",
  low: "Ranked, but a controller should read the trade-offs before acting.",
};

/**
 * Confidence as three segments rather than a percentage.
 *
 * A percentage would be a number, and a number on this page has to be
 * attested by a tool. `confidence` is a three-valued enum the ranking engine
 * sets, so it is drawn as three segments: the meter cannot imply a precision
 * the field does not have.
 */
export function ConfidenceMeter({ confidence }: { confidence: Confidence }) {
  const filled = CONFIDENCE_STEPS[confidence];
  const tone =
    confidence === "high" ? "bg-pass" : confidence === "medium" ? "bg-caution" : "bg-na";
  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={CONFIDENCE_NOTE[confidence]}
    >
      <span className="label-micro">Confidence</span>
      <span aria-label={`Confidence ${confidence}`} className="flex items-center gap-[3px]">
        {[1, 2, 3].map((step) => (
          <span
            key={step}
            className={cx(
              "block h-2.5 w-1.5 rounded-full",
              step <= filled ? tone : "bg-line",
            )}
          />
        ))}
      </span>
      <span className="text-xs text-ink-2 capitalize">{confidence}</span>
    </span>
  );
}

/* ===================================================== 7. context cards */

/**
 * A retrieved fact, with where it came from.
 *
 * The reference calls these context cards and shows a chunk of text with its
 * source underneath. The equivalent here is stronger, because a Fact is not a
 * chunk of prose: it is a value, a unit, a provenance, and, when the
 * provenance is `computed`, a derivation string the contract makes mandatory.
 * So the card can show the arithmetic that produced the number rather than
 * the paragraph the number was mentioned in, which is the difference between
 * a citation and a proof.
 */
export function ContextCard({ fact }: { fact: Fact }) {
  return (
    <article className="rounded-sm bg-surface px-3 py-2.5 flat">
      <div className="flex items-baseline gap-2">
        <span className="label-micro min-w-0 flex-1 truncate">{fact.label}</span>
        <ProvenanceDot provenance={fact.provenance} />
      </div>
      <p className="num mt-0.5 text-lg font-semibold text-ink">
        {factValue(fact.value, fact.unit)}
      </p>
      {fact.derivation ? (
        <p className="mono mt-1.5 text-xs leading-relaxed text-ink-2">
          {fact.derivation}
        </p>
      ) : null}
      <p className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-3">
        <DatabaseIcon size={10} weight="bold" aria-hidden />
        <span className="min-w-0 truncate">{fact.source}</span>
      </p>
    </article>
  );
}

function ProvenanceDot({ provenance }: { provenance: Fact["provenance"] }) {
  const colour =
    provenance === "dataset"
      ? "bg-ink-3"
      : provenance === "computed"
        ? "bg-accent"
        : "bg-caution";
  return (
    <span className="inline-flex items-center gap-1 text-2xs text-ink-3">
      <span aria-hidden className={cx("block size-1.5 rounded-full", colour)} />
      {PROVENANCE_LABEL[provenance]}
    </span>
  );
}

/** The source list under an answer: which dataset file, and where in it. */
export function SourceChip({ citation }: { citation: Citation }) {
  return (
    <span
      title={citation.note ?? undefined}
      className="inline-flex items-center gap-1.5 rounded-full bg-inset px-2 py-0.5 text-2xs text-ink-2"
    >
      <QuotesIcon size={10} weight="fill" aria-hidden className="text-ink-3" />
      <span className="mono">{citation.file}</span>
      <span className="mono text-ink-3">{citation.pointer}</span>
    </span>
  );
}

/* ===================================================== 8. insight cards */

/**
 * A paged insight, for the proactive brief.
 *
 * The reference pairs a headline figure with a scrubbable chart. There is no
 * time series in this dataset worth scrubbing, so the chart slot carries the
 * thing a controller actually scrubs: the severity mix across the watchlist,
 * as proportional segments. It is drawn from counts the brief returned and
 * sums to the total the brief returned.
 */
export function InsightCard({
  label,
  value,
  detail,
  segments,
  tone,
  onAsk,
  question,
}: {
  label: string;
  value: string;
  detail?: string;
  segments?: { tone: string; count: number; label: string }[];
  tone?: "breach" | "caution";
  onAsk?: (question: string) => void;
  question?: string | null;
}) {
  const total = (segments ?? []).reduce((sum, segment) => sum + segment.count, 0);
  return (
    <article className="flex flex-col gap-2 rounded-md bg-surface px-4 py-3 hairline">
      <p className="label-micro">{label}</p>
      <p
        className={cx(
          "num text-2xl leading-none font-semibold",
          tone === "breach" ? "text-breach" : tone === "caution" ? "text-caution" : "text-ink",
        )}
      >
        {value}
      </p>
      {segments && total > 0 ? (
        <span className="flex h-1.5 w-full overflow-hidden rounded-full bg-inset">
          {segments
            .filter((segment) => segment.count > 0)
            .map((segment) => (
              <span
                key={segment.label}
                title={`${segment.label}: ${segment.count}`}
                className={cx("block h-full", segment.tone)}
                style={{ width: `${(segment.count / total) * 100}%` }}
              />
            ))}
        </span>
      ) : null}
      {detail ? <p className="text-xs text-ink-3">{detail}</p> : null}
      {onAsk && question ? (
        <button
          type="button"
          onClick={() => onAsk(question)}
          className="mt-auto self-start text-xs text-accent-ink underline decoration-accent-line underline-offset-4 hover:decoration-current"
        >
          Ask about this
        </button>
      ) : null}
    </article>
  );
}

/* ============================================================= 9. hooks */

/**
 * Scroll a container to the bottom, but only while the reader is already
 * there. Yanking somebody back down while they are reading an earlier answer
 * is the single rudest thing a streaming chat can do, and it is what a plain
 * `scrollTo` on every token does.
 */
export function useStickToBottom(dep: unknown) {
  const ref = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const onScroll = () => {
      const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
      pinned.current = distance < 80;
    };
    node.addEventListener("scroll", onScroll, { passive: true });
    return () => node.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const node = ref.current;
    if (!node || !pinned.current) return;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [dep]);

  return ref;
}
