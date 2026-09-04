"use client";

/**
 * The boundary diagram, as a live component.
 *
 * Section 8 of the problem statement asks for an architecture diagram showing
 * where the language model stops and deterministic code starts. A picture of
 * one would be a claim; this is the claim with its own detail attached, node
 * by node, including what each stage is explicitly not allowed to do.
 *
 * The SVG paints from theme tokens so it is correct in both themes, carries a
 * title and description for screen readers, and every node is a real focusable
 * control. The same eight stages are listed below the drawing, so nothing in
 * the diagram is only reachable by pointing at it.
 */

import { useState } from "react";
import {
  CircleIcon,
  CpuIcon,
  ShieldCheckIcon,
  SparkleIcon,
} from "@phosphor-icons/react/dist/ssr";

import { Eyebrow, Pill, Token } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

type Zone = "io" | "model" | "deterministic" | "guard";

interface Node {
  id: string;
  x: number;
  y: number;
  zone: Zone;
  title: string;
  sub: string;
  pkg: string;
  summary: string;
  may: string[];
  mayNot: string[];
}

const W = 160;
const H = 56;

const NODES: Node[] = [
  {
    id: "question",
    x: 20,
    y: 56,
    zone: "io",
    title: "Question",
    sub: "plain language",
    pkg: "cli.py, web.py",
    summary:
      "Free text from the desk. Nothing is interpreted as a rule at this point, and no figure is extracted from it.",
    may: ["Arrive in any phrasing", "Refer back to earlier turns in the thread"],
    mayNot: ["Be treated as a source of facts"],
  },
  {
    id: "plan",
    x: 220,
    y: 56,
    zone: "model",
    title: "Agent: plan",
    sub: "LangGraph node",
    pkg: "agent/graph.py",
    summary:
      "The model reads the question and the thread, then decides which tools to call, with which arguments, in what order, and when it has enough to answer.",
    may: [
      "Choose tools and arguments",
      "Decide the order of the calls",
      "Decide it has enough, or that it must abstain",
    ],
    mayNot: [
      "State a number, identifier, date, station, amount or rule id",
      "Perform arithmetic, including approximation and unit conversion",
      "Infer a rule verdict instead of calling check_legality",
    ],
  },
  {
    id: "tools",
    x: 220,
    y: 196,
    zone: "deterministic",
    title: "Tool surface",
    sub: "17 tools, three tiers",
    pkg: "tools/registry.py",
    summary:
      "The seam. Every call returns a ToolEnvelope: a typed payload, a Fact for every figure in it, readable trace steps, and citations back into the dataset.",
    may: [
      "Return structured payloads and Facts",
      "Return ok=false with a specific error when a lookup fails",
    ],
    mayNot: [
      "Return free prose the model is expected to trust",
      "Return a numeric field with no matching Fact",
      "Return an empty result that reads like a negative finding",
    ],
  },
  {
    id: "engine",
    x: 420,
    y: 196,
    zone: "deterministic",
    title: "rules and ops",
    sub: "seven rules, costing, ranking",
    pkg: "rules/, ops/, domain/",
    summary:
      "Clock arithmetic, the seven rules, candidate enumeration, positioning, costing and ranking. This is the part a controller acts on, and no model runs inside it.",
    may: [
      "Compute every figure the system will ever state",
      "Produce a RuleTrace carrying the full arithmetic",
    ],
    mayNot: ["Import a model client. Ever."],
  },
  {
    id: "explain",
    x: 620,
    y: 56,
    zone: "model",
    title: "Agent: explain",
    sub: "LangGraph node",
    pkg: "agent/graph.py",
    summary:
      "The model turns computed results into something a controller can read at 6 a.m., choosing what to surface first and how to phrase the trade-off.",
    may: [
      "Choose phrasing and ordering",
      "Decide which facts matter most to this controller",
      "Rephrase a deterministic template",
    ],
    mayNot: [
      "Introduce an atom no tool produced this turn",
      "Soften a breach into a warning",
      "Turn insufficient data into a pass",
    ],
  },
  {
    id: "guard",
    x: 620,
    y: 336,
    zone: "guard",
    title: "Grounding guard",
    sub: "a graph node, not a prompt",
    pkg: "narrate/, verify/",
    summary:
      "Every number, identifier, date, currency amount and rule id in the drafted answer is matched against the Facts the tools returned this turn. One correction pass is allowed. After that the turn is refused.",
    may: [
      "Accept an answer where every atom is attested",
      "Send the turn back once for repair",
      "Reject the turn and force an abstention",
    ],
    mayNot: [
      "Be relaxed to let an unattested figure through",
      "Guess which fact a figure probably meant",
    ],
  },
  {
    id: "reply",
    x: 220,
    y: 336,
    zone: "io",
    title: "Reply or abstention",
    sub: "one type, every interface",
    pkg: "contracts/reply.py",
    summary:
      "A single Reply type carries the headline, the verified prose, rule traces, tables, impact, options, the guard's own report and the timings. The CLI, the HTTP layer and this console all render the same object.",
    may: ["Carry a refusal as a first class result"],
    mayNot: ["Contain a figure the guard did not attest"],
  },
];

const ZONE_FILL: Record<Zone, string> = {
  io: "var(--inset)",
  model: "var(--accent-tint)",
  deterministic: "var(--surface)",
  guard: "var(--pass-tint)",
};

const ZONE_STROKE: Record<Zone, string> = {
  io: "var(--line-strong)",
  model: "var(--accent-line)",
  deterministic: "var(--line-strong)",
  guard: "var(--pass-line)",
};

const ZONE_LABEL: Record<Zone, string> = {
  io: "Interface",
  model: "Language model",
  deterministic: "Deterministic",
  guard: "Guard",
};

export function ArchitectureView() {
  const [selected, setSelected] = useState<string>("guard");
  const node = NODES.find((n) => n.id === selected) ?? NODES[0];

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        <header>
          <Eyebrow>The boundary</Eyebrow>
          <h1 className="mt-1 text-xl font-semibold text-ink">
            The model plans and explains. It never produces a fact.
          </h1>
          <p className="mt-1.5 max-w-[72ch] text-md text-ink-2">
            Legality is exact arithmetic against a rulebook. A model that
            approximates a duty hour calculation produces answers that are
            fluent, confident and wrong, which is operationally worse than no
            answer. So the model decides what to compute and how to explain it,
            deterministic code computes, and a guard checks the result before a
            controller ever sees it. Select any stage to see what it may and
            may not do.
          </p>
        </header>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <Legend zone="model" icon={<SparkleIcon size={11} weight="fill" aria-hidden />} />
          <Legend
            zone="deterministic"
            icon={<CpuIcon size={11} weight="fill" aria-hidden />}
          />
          <Legend
            zone="guard"
            icon={<ShieldCheckIcon size={11} weight="fill" aria-hidden />}
          />
          <Legend zone="io" icon={<CircleIcon size={11} weight="fill" aria-hidden />} />
        </div>

        <figure className="mt-3 overflow-x-auto rounded-md bg-surface p-2 hairline">
          <svg
            viewBox="0 0 800 440"
            className="h-auto w-full min-w-[680px]"
            role="img"
            aria-labelledby="arch-title arch-desc"
          >
            <title id="arch-title">
              The language model and deterministic boundary
            </title>
            <desc id="arch-desc">
              A controller question reaches the agent, which plans and calls
              tools. The tool surface runs deterministic rules and operations
              code, which returns facts. The agent drafts an explanation, a
              grounding guard checks every figure in it against those facts,
              and the settled reply or an abstention is returned.
            </desc>

            <defs>
              <marker
                id="arrow"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ink-3)" />
              </marker>
              <marker
                id="arrow-accent"
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="6"
                markerHeight="6"
                orient="auto-start-reverse"
              >
                <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--caution)" />
              </marker>
            </defs>

            {/* zone bands */}
            <Band
              x={204}
              y={38}
              w={592}
              h={92}
              label="The model decides"
              stroke="var(--accent-line)"
              dashed
            />
            <Band
              x={204}
              y={178}
              w={392}
              h={92}
              label="No model, ever"
              stroke="var(--line-strong)"
            />
            <Band
              x={604}
              y={318}
              w={192}
              h={92}
              label="Checks the model"
              stroke="var(--pass-line)"
            />

            {/* edges */}
            <Edge d="M 180 84 H 214" label="asks" lx={197} ly={76} />
            <Edge d="M 292 112 V 190" label="calls" lx={286} ly={155} anchor="end" />
            <Edge
              d="M 316 190 V 116"
              dashed
              label="loops"
              lx={322}
              ly={155}
              anchor="start"
            />
            <Edge d="M 380 224 H 414" />
            <Edge
              d="M 580 224 H 700 V 118"
              label="facts, traces, citations"
              lx={704}
              ly={172}
              anchor="start"
            />
            <Edge d="M 700 112 V 330" label="every atom" lx={694} ly={250} anchor="end" />
            <Edge d="M 614 364 H 386" label="verified" lx={500} ly={356} />
            <Edge
              d="M 620 348 H 600 V 84 H 614"
              dashed
              caution
              label="one correction pass"
              lx={596}
              ly={310}
              anchor="end"
            />

            {/* nodes */}
            {NODES.map((n) => (
              <NodeShape
                key={n.id}
                node={n}
                selected={n.id === selected}
                onSelect={() => setSelected(n.id)}
              />
            ))}
          </svg>
        </figure>

        <section className="mt-4 grid gap-3 lg:grid-cols-[1fr_1.1fr]">
          <nav aria-label="Pipeline stages" className="space-y-1">
            {NODES.map((n, index) => (
              <button
                key={n.id}
                type="button"
                onClick={() => setSelected(n.id)}
                aria-current={n.id === selected ? "true" : undefined}
                className={cx(
                  "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left transition-colors duration-100",
                  n.id === selected ? "bg-accent-tint" : "hover:bg-hover",
                )}
              >
                <span className="num w-4 shrink-0 text-2xs text-ink-3">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 truncate text-base text-ink">
                  {n.title}
                </span>
                <Pill tone={n.zone === "model" ? "accent" : n.zone === "guard" ? "pass" : "na"}>
                  {ZONE_LABEL[n.zone]}
                </Pill>
              </button>
            ))}
          </nav>

          <article className="rounded-md bg-surface hairline">
            <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
              <h2 className="text-md font-semibold text-ink">{node.title}</h2>
              <Pill
                tone={
                  node.zone === "model"
                    ? "accent"
                    : node.zone === "guard"
                      ? "pass"
                      : "na"
                }
              >
                {ZONE_LABEL[node.zone]}
              </Pill>
              <Token>{node.pkg}</Token>
            </header>
            <p className="max-w-[68ch] px-3 py-2.5 text-base leading-relaxed text-ink-2">
              {node.summary}
            </p>
            <div className="grid gap-x-5 gap-y-3 border-t border-line-soft px-3 py-3 sm:grid-cols-2">
              <div>
                <Eyebrow>May</Eyebrow>
                <ul className="mt-1.5 space-y-1">
                  {node.may.map((item) => (
                    <li key={item} className="flex gap-2 text-base text-ink-2">
                      <span
                        aria-hidden
                        className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-pass"
                      />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <Eyebrow>May not</Eyebrow>
                <ul className="mt-1.5 space-y-1">
                  {node.mayNot.map((item) => (
                    <li key={item} className="flex gap-2 text-base text-ink-2">
                      <span
                        aria-hidden
                        className="mt-2 h-px w-2.5 shrink-0 bg-breach"
                      />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </article>
        </section>

        <section className="mt-6 grid gap-3 sm:grid-cols-3">
          <Claim
            title="Why not put the data in the prompt"
            body="It works for Tier 1 and fails at Tier 2 and 3. A duty hour window is exact arithmetic over a moving seven day span. An approximation is a violation, and a confident approximation is worse than a refusal."
          />
          <Claim
            title="Why the guard is a node, not an instruction"
            body="A prompt asking a model not to invent figures is a request. A graph node that matches every atom against the turn's facts and can reject the turn is a constraint. Only one of those holds under pressure."
          />
          <Claim
            title="Why the rejects are shown"
            body="A search you cannot see the shape of is indistinguishable from a guess. Showing the candidates that were excluded, each with the rule that excluded them, is what makes the ranking arguable."
          />
        </section>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ svg */

function NodeShape({
  node,
  selected,
  onSelect,
}: {
  node: Node;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <g
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      aria-label={`${node.title}, ${ZONE_LABEL[node.zone]}`}
      onClick={onSelect}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect();
        }
      }}
      className="cursor-pointer"
    >
      <rect
        x={node.x}
        y={node.y}
        width={W}
        height={H}
        rx={10}
        fill={ZONE_FILL[node.zone]}
        stroke={selected ? "var(--accent)" : ZONE_STROKE[node.zone]}
        strokeWidth={selected ? 2 : 1}
        strokeDasharray={node.zone === "model" ? "5 3" : undefined}
      />
      <text
        x={node.x + W / 2}
        y={node.y + 24}
        textAnchor="middle"
        fill="var(--ink)"
        fontSize="13.5"
        fontWeight="600"
      >
        {node.title}
      </text>
      <text
        x={node.x + W / 2}
        y={node.y + 41}
        textAnchor="middle"
        fill="var(--ink-3)"
        fontSize="10.5"
      >
        {node.sub}
      </text>
    </g>
  );
}

function Band({
  x,
  y,
  w,
  h,
  label,
  stroke,
  dashed,
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
  stroke: string;
  dashed?: boolean;
}) {
  return (
    <g aria-hidden>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={14}
        fill="none"
        stroke={stroke}
        strokeWidth={1}
        strokeDasharray={dashed ? "2 4" : "2 4"}
      />
      <text x={x + 10} y={y - 6} fill="var(--ink-3)" fontSize="10" letterSpacing="0.08em">
        {label.toUpperCase()}
      </text>
    </g>
  );
}

function Edge({
  d,
  label,
  lx,
  ly,
  anchor = "middle",
  dashed,
  caution,
}: {
  d: string;
  label?: string;
  lx?: number;
  ly?: number;
  anchor?: "start" | "middle" | "end";
  dashed?: boolean;
  caution?: boolean;
}) {
  return (
    <g aria-hidden>
      <path
        d={d}
        fill="none"
        stroke={caution ? "var(--caution)" : "var(--ink-3)"}
        strokeWidth={1.25}
        strokeDasharray={dashed ? "4 3" : undefined}
        markerEnd={caution ? "url(#arrow-accent)" : "url(#arrow)"}
      />
      {label && lx !== undefined && ly !== undefined ? (
        <text
          x={lx}
          y={ly}
          textAnchor={anchor}
          fill="var(--ink-3)"
          fontSize="9.5"
          letterSpacing="0.04em"
        >
          {label}
        </text>
      ) : null}
    </g>
  );
}

function Legend({ zone, icon }: { zone: Zone; icon: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      <span
        aria-hidden
        className={cx(
          "inline-flex h-4 w-4 items-center justify-center rounded-xs",
          zone === "model"
            ? "bg-accent-tint text-accent"
            : zone === "guard"
              ? "bg-pass-tint text-pass"
              : zone === "deterministic"
                ? "bg-surface text-ink-2 ring-1 ring-line-strong"
                : "bg-inset text-ink-3 ring-1 ring-line",
        )}
      >
        {icon}
      </span>
      {ZONE_LABEL[zone]}
    </span>
  );
}

function Claim({ title, body }: { title: string; body: string }) {
  return (
    <article className="rounded-md bg-surface px-3 py-2.5 hairline">
      <h3 className="text-base font-semibold text-ink">{title}</h3>
      <p className="mt-1 text-base leading-relaxed text-ink-2">{body}</p>
    </article>
  );
}
