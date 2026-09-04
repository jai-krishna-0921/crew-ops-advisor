"use client";

/**
 * Operations: the deterministic engine, with the model removed.
 *
 * Every panel here calls a route that never invokes a language model. Unset
 * the API key and this page behaves identically, which is the point: the
 * rules engine is the product, and the agent is the way a controller reaches
 * it in plain language.
 */

import { useCallback, useEffect, useState } from "react";
import {
  CircleDashedIcon,
  GavelIcon,
  ListMagnifyingGlassIcon,
  PlayIcon,
  ScalesIcon,
  StackIcon,
} from "@phosphor-icons/react/dist/ssr";

import type {
  ImpactReport,
  LegalityReport,
  Recommendation,
  RuleDefinition,
  WorldSummary,
} from "@/lib/contracts";
import { api } from "@/lib/api";
import { collectFacts } from "@/lib/fact-link";
import { dateTime, grouped, longDate, withUnit } from "@/lib/format";
import { RecommendationView } from "@/components/answer/cover-options";
import { ImpactReportView } from "@/components/answer/impact-report";
import { LegalityReportView } from "@/components/answer/rule-trace";
import { FactProvider } from "@/components/evidence/fact-context";
import {
  EmptyState,
  Eyebrow,
  Panel,
  PanelHead,
  Pill,
  Segmented,
  Skeleton,
  Token,
} from "@/components/ui/primitives";

type Tab = "rules" | "legality" | "cover" | "simulate";

const CREW = [
  { id: "C-3310", label: "C-3310, R. Menon, reserve, clean on both days" },
  { id: "C-2210", label: "C-2210, S. Iyer, DEL based, legal with positioning" },
  { id: "C-2087", label: "C-2087, V. Krishnan, RULE-DUTY-02 breach on day 2" },
  { id: "C-3305", label: "C-3305, M. Pillai, legal day 1, breaches day 2" },
  { id: "C-2091", label: "C-2091, T. Fernandes, ATR72 only" },
  { id: "C-4188", label: "C-4188, G. Sundaram, short of minimum rest" },
];


/**
 * A fetch keyed by its inputs.
 *
 * Loading is derived from whether the stored result answers the current key,
 * so the effect body only talks to the network. Re-running the same inputs is
 * a nonce bump, which is an event, not an effect.
 */
interface Keyed<T> {
  key: string;
  data: T | null;
  error: string | null;
}

function useKeyedFetch<T>(key: string, fetcher: () => Promise<T>) {
  const [result, setResult] = useState<Keyed<T> | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetcher()
      .then((data) => {
        if (!cancelled) setResult({ key, data, error: null });
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setResult({
          key,
          data: null,
          error:
            cause instanceof Error ? cause.message : "The request failed.",
        });
      });
    return () => {
      cancelled = true;
    };
  }, [key, fetcher]);

  const fresh = result?.key === key ? result : null;
  return {
    data: fresh?.data ?? null,
    error: fresh?.error ?? null,
    busy: fresh === null,
  };
}

export function OpsView() {
  const [tab, setTab] = useState<Tab>("rules");
  const [world, setWorld] = useState<WorldSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .worldSummary()
      .then((value) => {
        if (!cancelled) setWorld(value);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="anim-fade-up mx-auto max-w-5xl px-6 pt-10 pb-14 sm:px-10">
        <header>
          <Eyebrow>Deterministic panels</Eyebrow>
          <h1 className="mt-1 text-2xl font-medium text-ink">Operations</h1>
          <p className="mt-1 max-w-[72ch] text-md text-ink-2">
            Nothing on this page calls a language model. These routes are the
            engine the agent reaches through, exposed directly so the rules can
            be checked without a conversation in the way.
          </p>
        </header>

        <WorldStrip world={world} />

        <div className="mt-4">
          <Segmented
            label="Operations panel"
            value={tab}
            onChange={setTab}
            options={[
              { value: "rules", label: "Rulebook" },
              { value: "legality", label: "Legality" },
              { value: "cover", label: "Cover search" },
              { value: "simulate", label: "Simulation" },
            ]}
          />
        </div>

        <div className="mt-4">
          {tab === "rules" ? <RulesPanel /> : null}
          {tab === "legality" ? <LegalityPanel /> : null}
          {tab === "cover" ? <CoverPanel /> : null}
          {tab === "simulate" ? <SimulatePanel /> : null}
        </div>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- world */

function WorldStrip({ world }: { world: WorldSummary | null }) {
  if (!world) {
    return (
      <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-14 w-full" />
        ))}
      </div>
    );
  }
  // A panel should degrade, not take the page down, if a field it wanted is
  // absent. Object.entries throws on undefined.
  const entries = Object.entries(world.counts ?? {}).slice(0, 6);
  return (
    <div className="mt-4">
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {entries.map(([key, value]) => (
          <div key={key} className="rounded-md bg-surface px-2.5 py-2 hairline">
            <p className="label-micro">{key}</p>
            <p className="num mt-0.5 text-lg font-semibold text-ink">
              {grouped(value)}
            </p>
          </div>
        ))}
      </div>
      <p className="num mt-2 text-xs text-ink-3">
        {world.operator ?? "Operator"} · hub {world.base} ·{" "}
        {longDate(world.date_from)} to {longDate(world.date_to)} · snapshot{" "}
        {dateTime(world.snapshot)}Z · {world.currency ?? "INR"}
      </p>
    </div>
  );
}

/* --------------------------------------------------------------- rules */

function RulesPanel() {
  const [rules, setRules] = useState<RuleDefinition[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .rules()
      .then((value) => {
        if (!cancelled) setRules(value);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (!rules) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  return (
    <section aria-label="The rulebook" className="space-y-2">
      <p className="max-w-[72ch] text-base text-ink-2">
        Seven rules, as shipped in <span className="num">rules.json</span>.
        There is no eighth rule, and the system will say so rather than invent
        one.
      </p>
      {rules.map((rule) => (
        <article key={rule.rule_id} className="rounded-md bg-surface hairline">
          <header className="flex flex-wrap items-center gap-2 px-3 py-2">
            <Token>{rule.rule_id}</Token>
            <h2 className="text-md font-medium text-ink">{rule.title}</h2>
            {rule.limit !== null && rule.limit !== undefined ? (
              <Pill tone="accent">{withUnit(rule.limit, rule.unit)}</Pill>
            ) : (
              <Pill tone="na">{rule.unit ?? "qualitative"}</Pill>
            )}
          </header>
          <p className="px-3 py-2 text-base text-ink">{rule.constraint}</p>
          {rule.detail ? (
            <p className="max-w-[72ch] whitespace-pre-line px-3 py-2 text-base leading-relaxed text-ink-2">
              {rule.detail}
            </p>
          ) : null}
        </article>
      ))}
    </section>
  );
}

/* ------------------------------------------------------------ legality */

function LegalityPanel() {
  const [crewId, setCrewId] = useState(CREW[2].id);
  const [assignment, setAssignment] = useState("P-2291");
  const [nonce, setNonce] = useState(0);

  const key = `${crewId}|${assignment}|${nonce}`;
  const fetcher = useCallback(
    () => api.legality({ crew_id: crewId, pairing_id: assignment }),
    [crewId, assignment],
  );
  const { data: report, error, busy } = useKeyedFetch<LegalityReport>(key, fetcher);

  const facts = report
    ? collectFacts(
        ...report.per_day.flatMap((day) => day.traces.map((trace) => trace.inputs)),
      )
    : [];

  return (
    <section aria-label="Legality checker" className="space-y-3">
      <Panel>
        <PanelHead
          title="Legality checker"
          meta="All seven rules, per duty day"
          icon={<ScalesIcon size={13} weight="bold" aria-hidden />}
        />
        <div className="flex flex-wrap items-end gap-3 px-3 py-3">
          <Field label="Crew">
            <select
              value={crewId}
              onChange={(event) => setCrewId(event.target.value)}
              className="num w-72 rounded-sm bg-inset px-2 py-1 text-base text-ink outline-none"
            >
              {CREW.map((crew) => (
                <option key={crew.id} value={crew.id}>
                  {crew.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Assignment">
            <input
              value={assignment}
              onChange={(event) => setAssignment(event.target.value)}
              className="num w-32 rounded-sm bg-inset px-2 py-1 text-base text-ink outline-none"
            />
          </Field>
          <button
            type="button"
            onClick={() => setNonce((n) => n + 1)}
            disabled={busy}
            className="inline-flex h-7 items-center gap-1.5 rounded-sm bg-accent px-2.5 text-base font-medium text-page transition-opacity duration-100 disabled:opacity-50"
          >
            {busy ? (
              <CircleDashedIcon
                size={12}
                weight="bold"
                aria-hidden
                className="anim-spin"
              />
            ) : (
              <GavelIcon size={12} weight="bold" aria-hidden />
            )}
            Check
          </button>
        </div>
      </Panel>

      {error ? (
        <EmptyState title="The check could not run" detail={error} />
      ) : report ? (
        <FactProvider facts={facts} drawerOpen={false} setDrawerOpen={() => undefined}>
          <LegalityReportView report={report} />
        </FactProvider>
      ) : (
        <Skeleton className="h-32 w-full" />
      )}
    </section>
  );
}

/* --------------------------------------------------------------- cover */

function CoverPanel() {
  const [pairing, setPairing] = useState("P-2291");
  const [nonce, setNonce] = useState(0);

  const key = `${pairing}|${nonce}`;
  const fetcher = useCallback(
    () => api.cover({ pairing_id: pairing, include_rejected: true, max_options: 5 }),
    [pairing],
  );
  const {
    data: recommendation,
    error,
    busy,
  } = useKeyedFetch<Recommendation>(key, fetcher);

  const facts = recommendation ? collectFacts(recommendation.facts) : [];

  return (
    <section aria-label="Cover search" className="space-y-3">
      <Panel>
        <PanelHead
          title="Cover search"
          meta="Enumerate, check, price and rank"
          icon={<ListMagnifyingGlassIcon size={13} weight="bold" aria-hidden />}
        />
        <div className="flex flex-wrap items-end gap-3 px-3 py-3">
          <Field label="Pairing">
            <input
              value={pairing}
              onChange={(event) => setPairing(event.target.value)}
              className="num w-32 rounded-sm bg-inset px-2 py-1 text-base text-ink outline-none"
            />
          </Field>
          <button
            type="button"
            onClick={() => setNonce((n) => n + 1)}
            disabled={busy}
            className="inline-flex h-7 items-center gap-1.5 rounded-sm bg-accent px-2.5 text-base font-medium text-page transition-opacity duration-100 disabled:opacity-50"
          >
            {busy ? (
              <CircleDashedIcon
                size={12}
                weight="bold"
                aria-hidden
                className="anim-spin"
              />
            ) : (
              <StackIcon size={12} weight="bold" aria-hidden />
            )}
            Search
          </button>
        </div>
      </Panel>

      {error ? (
        <EmptyState title="The search could not run" detail={error} />
      ) : recommendation ? (
        <FactProvider facts={facts} drawerOpen={false} setDrawerOpen={() => undefined}>
          <RecommendationView recommendation={recommendation} />
        </FactProvider>
      ) : (
        <Skeleton className="h-32 w-full" />
      )}
    </section>
  );
}

/* ------------------------------------------------------------ simulate */

function SimulatePanel() {
  const [crewId, setCrewId] = useState("C-1042");
  const [fromDate, setFromDate] = useState("2026-09-15");
  const [nonce, setNonce] = useState(0);

  const key = `${crewId}|${fromDate}|${nonce}`;
  const fetcher = useCallback(
    () =>
      api.simulate({
        kind: "crew_absence",
        crew_id: crewId,
        from_date: fromDate,
      }),
    [crewId, fromDate],
  );
  const { data: impact, error, busy } = useKeyedFetch<ImpactReport>(key, fetcher);

  const facts = impact ? collectFacts(impact.facts) : [];

  return (
    <section aria-label="Disruption simulation" className="space-y-3">
      <Panel>
        <PanelHead
          title="Absence simulation"
          meta="What breaks, and what breaks next"
          icon={<PlayIcon size={13} weight="bold" aria-hidden />}
        />
        <div className="flex flex-wrap items-end gap-3 px-3 py-3">
          <Field label="Crew">
            <input
              value={crewId}
              onChange={(event) => setCrewId(event.target.value)}
              className="num w-32 rounded-sm bg-inset px-2 py-1 text-base text-ink outline-none"
            />
          </Field>
          <Field label="From date">
            <input
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
              className="num rounded-sm bg-inset px-2 py-1 text-base text-ink outline-none"
            />
          </Field>
          <button
            type="button"
            onClick={() => setNonce((n) => n + 1)}
            disabled={busy}
            className="inline-flex h-7 items-center gap-1.5 rounded-sm bg-accent px-2.5 text-base font-medium text-page transition-opacity duration-100 disabled:opacity-50"
          >
            {busy ? (
              <CircleDashedIcon
                size={12}
                weight="bold"
                aria-hidden
                className="anim-spin"
              />
            ) : (
              <PlayIcon size={12} weight="bold" aria-hidden />
            )}
            Simulate
          </button>
        </div>
      </Panel>

      {error ? (
        <EmptyState title="The simulation could not run" detail={error} />
      ) : impact ? (
        <FactProvider facts={facts} drawerOpen={false} setDrawerOpen={() => undefined}>
          <ImpactReportView impact={impact} />
        </FactProvider>
      ) : (
        <Skeleton className="h-32 w-full" />
      )}
    </section>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="label-micro block">{label}</span>
      <span className="mt-1 block">{children}</span>
    </label>
  );
}
