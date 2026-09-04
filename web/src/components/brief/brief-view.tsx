"use client";

/**
 * The morning brief.
 *
 * This is the screen a controller has open before anyone asks them anything.
 * It is produced deterministically, with no model involved, which is why it
 * still works with the API key unset.
 *
 * Every alert carries the question that investigates it, so the brief is a
 * launchpad rather than a wall of warnings.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ArrowRightIcon, CalendarBlankIcon } from "@phosphor-icons/react/dist/ssr";

import type { Alert, RiskSeverity, Watchlist } from "@/lib/contracts";
import { api } from "@/lib/api";
import { collectFacts } from "@/lib/fact-link";
import {
  dateTime,
  grouped,
  longDate,
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  SEVERITY_TONE,
  shortDate,
} from "@/lib/format";
import { GroundedText } from "@/components/answer/grounded-prose";
import { FactProvider } from "@/components/evidence/fact-context";
import {
  EmptyState,
  Eyebrow,
  Pill,
  Segmented,
  Skeleton,
  Token,
} from "@/components/ui/primitives";
import { cx, TONE } from "@/components/ui/tone";

const DATES = [
  "2026-09-15",
  "2026-09-16",
  "2026-09-17",
  "2026-09-18",
  "2026-09-19",
  "2026-09-20",
];

type Filter = "all" | RiskSeverity;

interface BriefResult {
  date: string;
  watchlist: Watchlist | null;
  error: string | null;
}

export function BriefView() {
  const [date, setDate] = useState(DATES[0]);
  const [filter, setFilter] = useState<Filter>("all");

  /**
   * One state object keyed by the date it answers. Loading is derived from
   * that key rather than flipped in an effect, so the effect body talks only
   * to the network and never to React state.
   */
  const [result, setResult] = useState<BriefResult | null>(null);
  const fresh = result?.date === date ? result : null;
  const loading = fresh === null;
  const watchlist = fresh?.watchlist ?? null;
  const error = fresh?.error ?? null;

  useEffect(() => {
    let cancelled = false;
    api
      .brief(date)
      .then((value) => {
        if (!cancelled) setResult({ date, watchlist: value, error: null });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setResult({
          date,
          watchlist: null,
          error:
            cause instanceof Error
              ? cause.message
              : "The brief could not be loaded.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [date]);

  const counts = useMemo(() => {
    const by: Record<RiskSeverity, number> = {
      critical: 0,
      high: 0,
      medium: 0,
      low: 0,
    };
    for (const alert of watchlist?.alerts ?? []) by[alert.severity] += 1;
    return by;
  }, [watchlist]);

  const alerts = useMemo(() => {
    const list = [...(watchlist?.alerts ?? [])].sort(
      (a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
    );
    return filter === "all" ? list : list.filter((a) => a.severity === filter);
  }, [watchlist, filter]);

  const facts = useMemo(
    () => collectFacts(...(watchlist?.alerts ?? []).map((alert) => alert.facts)),
    [watchlist],
  );

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <Eyebrow>Proactive watchlist</Eyebrow>
            <h1 className="mt-1 text-xl font-semibold text-ink">
              Morning brief, {longDate(date)}
            </h1>
            {watchlist ? (
              <p className="mt-1 max-w-[68ch] text-md text-ink-2">
                {watchlist.headline}
              </p>
            ) : null}
          </div>

          <label className="flex items-center gap-1.5">
            <CalendarBlankIcon
              size={13}
              weight="bold"
              aria-hidden
              className="text-ink-3"
            />
            <span className="sr-only">Brief date</span>
            <select
              value={date}
              onChange={(event) => setDate(event.target.value)}
              className="num rounded-sm bg-inset px-2 py-1 text-base text-ink ring-1 ring-line outline-none"
            >
              {DATES.map((value) => (
                <option key={value} value={value}>
                  {longDate(value)}
                </option>
              ))}
            </select>
          </label>
        </header>

        {watchlist ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <Segmented
              label="Filter by severity"
              value={filter}
              onChange={setFilter}
              options={[
                { value: "all", label: "All", count: watchlist.alerts.length },
                { value: "critical", label: "Critical", count: counts.critical },
                { value: "high", label: "High", count: counts.high },
                { value: "medium", label: "Medium", count: counts.medium },
                { value: "low", label: "Low", count: counts.low },
              ]}
            />
            <p className="num text-xs text-ink-3">
              Scanned{" "}
              {Object.entries(watchlist.scanned)
                .map(([key, value]) => `${grouped(value)} ${key}`)
                .join(", ")}{" "}
              as at {dateTime(watchlist.as_of)}Z
            </p>
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {loading ? (
            <>
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </>
          ) : error ? (
            <EmptyState
              title="The brief could not be loaded"
              detail={error}
            />
          ) : alerts.length === 0 ? (
            <EmptyState
              title="Nothing at this severity"
              detail="Change the filter, or pick another date. An empty brief is a finding, not a failure."
            />
          ) : (
            <FactProvider
              facts={facts}
              drawerOpen={false}
              setDrawerOpen={() => undefined}
            >
              {alerts.map((alert, index) => (
                <AlertRow key={`${alert.title}-${index}`} alert={alert} />
              ))}
            </FactProvider>
          )}
        </div>

        <p className="mt-6 max-w-[68ch] text-xs text-ink-3">
          The brief is produced by deterministic code. No language model is
          involved in deciding what appears here or in wording it, which is why
          it still runs with no API key configured.
        </p>
      </div>
    </div>
  );
}

function AlertRow({ alert }: { alert: Alert }) {
  const tone = SEVERITY_TONE[alert.severity];
  return (
    <article
      className={cx("rounded-md bg-surface hairline", TONE[tone].edge)}
    >
      <div className="flex flex-wrap items-start gap-x-2 gap-y-1.5 px-3 py-2.5">
        <Pill tone={tone}>{SEVERITY_LABEL[alert.severity]}</Pill>
        <h2 className="min-w-0 flex-1 text-md font-medium text-ink">
          <GroundedText text={alert.title} facts={alert.facts} />
        </h2>
        {alert.due_date ? (
          <span className="num shrink-0 text-xs text-ink-3">
            due {shortDate(alert.due_date)}
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 px-3 pb-2">
        {alert.crew_id ? <Token>{alert.crew_id}</Token> : null}
        {alert.flight_no ? <Token>{alert.flight_no}</Token> : null}
        {alert.pairing_id ? <Token>{alert.pairing_id}</Token> : null}
        {alert.rule_id ? <Token>{alert.rule_id}</Token> : null}
      </div>

      <p className="max-w-[72ch] px-3 pb-2.5 text-base leading-relaxed text-ink-2">
        <GroundedText text={alert.detail} facts={alert.facts} />
      </p>

      {alert.suggested_question ? (
        <div className="border-t border-line-soft px-3 py-2">
          <Link
            href={`/?q=${encodeURIComponent(alert.suggested_question)}`}
            className="group inline-flex items-center gap-1.5 text-base text-accent"
          >
            {alert.suggested_question}
            <ArrowRightIcon
              size={11}
              weight="bold"
              aria-hidden
              className="transition-transform duration-150 group-hover:translate-x-0.5"
            />
          </Link>
        </div>
      ) : null}
    </article>
  );
}
