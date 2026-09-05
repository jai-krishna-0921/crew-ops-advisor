"use client";

/**
 * The landing page.
 *
 * THE FIRST VERSION OF THIS WAS THE TEMPLATE AND NOTHING ELSE. Centred eyebrow
 * pill, centred enormous headline with a gradient on two words of it, centred
 * subtitle, two centred buttons, a card underneath. Every section after it the
 * same shape. It was competent and it was the exact page a generator produces,
 * which is a problem for a product whose whole pitch is that it does not take
 * the plausible route.
 *
 * Three things changed, and they are the reasons this reads as built rather
 * than assembled.
 *
 * **The page is asymmetric.** The hero is set left with the evidence stacked
 * to the right of it at three depths, and nothing below is centred except the
 * one line that earns it. A centred column is the shape of a page that has not
 * decided what matters.
 *
 * **The scroll does something.** The three tiers are a horizontal track: the
 * section pins to the window and the cards walk left while the reader scrolls
 * down, on a CSS scroll timeline rather than a scroll listener. Layers in the
 * hero and the footer drift against the scroll at different rates.
 *
 * **The copy has a voice.** "The model plans and explains, deterministic code
 * computes" is accurate and reads like a datasheet. What it actually means is
 * that the model is not allowed to do the maths, and saying that is both
 * shorter and truer to how anybody would explain it out loud.
 *
 * THE NUMBERS ARE DATASET FACTS, NOT SCORES. 147 flights, 150 crew, 39
 * pairings, 7 rules are counts of `data/`, which is read only by project rule
 * and cannot drift. There is deliberately no accuracy figure anywhere here:
 * `PROGRESS.md` records the same model scoring 16, 15 and 16 on three
 * identical passes, and a landing page is the surface nobody returns to
 * update, so a score printed here would be quietly false within a week. The
 * claims made instead are about the mechanism, which does not move.
 */

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import {
  ArrowRightIcon,
  ArrowUpRightIcon,
  CheckCircleIcon,
} from "@phosphor-icons/react/dist/ssr";

import { Reveal, revealClasses, useInView } from "@/components/landing/reveal";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Button, ButtonLink } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------------------ content */

/** The ticker. Counts of `data/`, and one claim about the mechanism. */
const TICKER = [
  "147 flights",
  "150 crew",
  "39 pairings",
  "16 reserves",
  "7 rules",
  "6 worked scenarios",
  "38 questions with answer keys",
  "zero unattested figures",
  "cheapest legal option found in <2s",
  "one week, all times UTC",
];

const MAY = [
  "Work out which computations the question needs, and in what order",
  "Read what came back and write the explanation somebody acts on",
  "Notice that a question is harder than it looked, and go deeper",
  "Give up, and say exactly what it was missing",
];

const MAY_NOT = [
  "State a figure no tool returned",
  "Do arithmetic. Even the easy kind. Especially the easy kind",
  "Decide whether an assignment is legal",
  "Name a crew member the tools never surfaced",
];

/** The seven, verbatim from `rules.json` by way of the operations page. */
const RULES = [
  {
    id: "RULE-FDP-01",
    title: "Maximum flight duty period",
    limit: "13h",
    constraint: "Max flight duty period 13h, reduced 0.5h per sector beyond the 2nd.",
    note: "P-2291 day 1 flies 3 sectors, so the limit is 13.0 minus 0.5, which is 12.5h. The duty runs 06:00Z to 15:30Z, 9.50h, legal with 3.00h spare.",
  },
  {
    id: "RULE-DUTY-02",
    title: "Maximum duty hours per 7 calendar days",
    limit: "60h",
    constraint:
      "Max 60 duty hours in any 7 consecutive calendar days, inclusive of the duty date.",
    note: "The rule that rules C-2087 out of covering P-2291. 51.83h already in the window, plus 9.50h of cover, is 61.33h against 60h. Over by 1h20m, which is not close enough to wave through.",
  },
  {
    id: "RULE-FLT-03",
    title: "Maximum block hours per 28 calendar days",
    limit: "100h",
    constraint: "Max 100 flight (block) hours in any 28 consecutive calendar days.",
    note: "The highest 28 day block total anywhere in this dataset is 79.28h, so this rule binds on nobody. It is still checked on every assignment, and the trace still says it was, because a controller cannot tell 'checked, fine' from 'never checked' if the answer stays quiet about it.",
  },
  {
    id: "RULE-REST-04",
    title: "Minimum rest between duties",
    limit: "12h",
    constraint: "Min 12h rest between release and next report.",
    note: "Released 15:30Z on 16 Sep, may report from 03:30Z on 17 Sep. The comparison is strict, so exactly 12.0h is legal and 11h59m is not.",
  },
  {
    id: "RULE-QUAL-05",
    title: "Aircraft type rating",
    limit: "qualitative",
    constraint: "Crew must hold a valid rating for the assigned aircraft type.",
    note: "C-2091 is rated on the ATR72 and nothing else, so every A320 pairing excludes them. A rating is a fact in the dataset, never an inference from what somebody happens to have flown before.",
  },
  {
    id: "RULE-CERT-06",
    title: "Certification validity",
    limit: "qualitative",
    constraint: "All certifications must be valid on the duty date.",
    note: "C-5417's recurrent training lapses mid roster, which makes the same assignment legal on Tuesday and illegal on Thursday. This is why cover is checked on every day of a pairing rather than on the first one.",
  },
  {
    id: "RULE-BASE-07",
    title: "Reserve callout from base",
    limit: "qualitative",
    constraint: "Reserve callout from base only, unless deadhead cost is applied.",
    note: "C-2210 sits at DEL. They are a legal option for a BLR pairing the moment positioning is costed, and that cost goes on the option itself rather than into a footnote nobody reads.",
  },
];

type CapabilityValues = Record<string, string>;

type Capability = {
  id: string;
  label: string;
  description: string;
  fields: readonly {
    key: string;
    label: string;
    placeholder: string;
    type?: "text" | "date";
  }[];
  buildQuestion: (values: CapabilityValues) => string;
};

/** Generic entry points. The user supplies the operational facts before chat. */
const TIER_LADDER: readonly {
  n: string;
  name: string;
  definition: string;
  tint: number;
  capabilities: readonly Capability[];
}[] = [
  {
    n: "01",
    name: "Lookup",
    definition: "Retrieves a fact directly from the supplied dataset.",
    tint: 1,
    capabilities: [
      {
        id: "find-reserves",
        label: "Find available reserves",
        description: "See who is on call at a base on a given date.",
        fields: [
          { key: "station", label: "Base", placeholder: "Station code" },
          { key: "date", label: "Date", placeholder: "", type: "date" },
        ],
        buildQuestion: ({ station, date }) =>
          `Who is on reserve at ${station} on ${date}, and what are their on-call windows?`,
      },
      {
        id: "duty-headroom",
        label: "Check duty headroom",
        description: "Check accrued duty and remaining seven-day headroom.",
        fields: [
          { key: "crew", label: "Crew ID", placeholder: "Crew ID" },
          { key: "date", label: "As of date", placeholder: "", type: "date" },
        ],
        buildQuestion: ({ crew, date }) =>
          `As of ${date}, how many duty hours has ${crew} accrued in the previous 7 calendar days, and how much headroom remains under RULE-DUTY-02?`,
      },
    ],
  },
  {
    n: "02",
    name: "Consequence",
    definition: "Computes what changes, what breaks, and which rule binds.",
    tint: 2,
    capabilities: [
      {
        id: "sick-call",
        label: "Simulate a sick call",
        description: "See which flights lose cover when a crew member is unavailable.",
        fields: [
          { key: "crew", label: "Crew ID", placeholder: "Crew ID" },
          { key: "date", label: "Date", placeholder: "", type: "date" },
        ],
        buildQuestion: ({ crew, date }) =>
          `${crew} calls in sick on ${date}. Which flights are immediately uncrewed?`,
      },
      {
        id: "cover-legality",
        label: "Check cover legality",
        description: "Test a crew assignment against all seven rules.",
        fields: [
          { key: "crew", label: "Crew ID", placeholder: "Crew ID" },
          { key: "pairing", label: "Pairing ID", placeholder: "Pairing ID" },
          { key: "date", label: "Start date", placeholder: "", type: "date" },
        ],
        buildQuestion: ({ crew, pairing, date }) =>
          `If ${crew} is assigned to cover ${pairing} from ${date}, does any rule breach? Give the detail.`,
      },
    ],
  },
  {
    n: "03",
    name: "Recommendation",
    definition: "Ranks legal options by their explicit operational trade-offs.",
    tint: 4,
    capabilities: [
      {
        id: "rank-cover",
        label: "Rank cover options",
        description: "Compare legal cover choices by cost and operational impact.",
        fields: [
          { key: "crew", label: "Unavailable crew ID", placeholder: "Crew ID" },
          { key: "pairing", label: "Pairing ID", placeholder: "Pairing ID" },
          { key: "date", label: "Start date", placeholder: "", type: "date" },
        ],
        buildQuestion: ({ crew, pairing, date }) =>
          `${crew} is out for ${pairing} from ${date}. Produce ranked resolution options with costs and reasoning.`,
      },
      {
        id: "joint-cover",
        label: "Resolve multiple absences",
        description: "Build one crewing plan for two unavailable crew members.",
        fields: [
          { key: "firstCrew", label: "First crew ID", placeholder: "Crew ID" },
          { key: "secondCrew", label: "Second crew ID", placeholder: "Crew ID" },
          { key: "date", label: "Date", placeholder: "", type: "date" },
        ],
        buildQuestion: ({ firstCrew, secondCrew, date }) =>
          `${firstCrew} and ${secondCrew} are both unavailable on ${date}. Give the optimal joint crewing plan.`,
      },
    ],
  },
];

const NAV = [
  { href: "#boundary", label: "The boundary" },
  { href: "#work", label: "What it does" },
  { href: "#rules", label: "The rules" },
];

/* ------------------------------------------------------------------- pieces */

/**
 * A heading whose words arrive one after another.
 *
 * Split on spaces and each word wrapped, because a heading that fades in as
 * one block is a heading that appeared, and one that arrives left to right is
 * a heading being written. The delay is small: 40ms across seven words is
 * under a third of a second, which reads as one gesture rather than as seven
 * animations.
 *
 * `inline-block` on the word and `overflow-hidden` on the wrapper is what
 * makes it a mask rather than a fade: the word rises out from behind the line
 * above it. Descenders would be clipped, so the wrapper carries the leading as
 * padding and pulls it back with a negative margin.
 *
 * ONE OBSERVER, ON THE HEADING, NOT ONE PER WORD. That mask clips the word to
 * nothing while it is hidden, and IntersectionObserver accounts for clipping
 * by an ancestor's overflow, so a word watching itself can never see itself
 * arrive: the mask hides it, the observer reports zero area, and it stays
 * hidden forever. It only appeared to work at desktop size, where the word was
 * taller than the 40px of travel and a sliver stayed inside the clip box; at
 * the smaller mobile heading size every word vanished for good. The heading is
 * never hidden, so the heading is the thing to watch.
 */
function Words({
  text,
  className,
  from = 0,
}: {
  text: string;
  className?: string;
  from?: number;
}) {
  const { ref, shown } = useInView<HTMLSpanElement>();
  const words = text.split(" ");

  return (
    <span ref={ref} className={className}>
      {words.map((word, index) => (
        <span
          key={`${word}-${index}`}
          className={cn(
            "inline-block -mb-[0.22em] overflow-hidden pb-[0.22em] align-bottom",
            // THE WORD SPACE IS A MARGIN, NOT A SPACE. A trailing space inside
            // an inline-block is trimmed, so rendering it after the word ran
            // the heading together as "Itgoesasfarasthe". A margin cannot be
            // collapsed away.
            index < words.length - 1 && "me-[0.25em]",
          )}
        >
          <span
            style={{ transitionDelay: `${from + index * 40}ms` }}
            className={cn(revealClasses(shown), "inline-block")}
          >
            {word}
          </span>
        </span>
      ))}
    </span>
  );
}

/* --------------------------------------------------------------------- page */

export function Landing() {
  return (
    /* `isolate` is load bearing. The aurora sits at `z-index: -1` so nothing
       else needs a z-index at all, and without a stacking context here a
       negative layer paints before this element's own background, so `bg-page`
       covered the lights and the page rendered flat. */
    <div className="relative isolate min-h-[100dvh] overflow-x-clip bg-page">
      <div aria-hidden className="aurora" />
      <div aria-hidden className="grain" />

      {/* How far down the page the reader is, drawn as a hairline across the
          top. It is on a scroll timeline like everything else here, so it
          costs nothing and cannot fall out of step with the scroll it is
          reporting. */}
      <div
        aria-hidden
        className="pointer-events-none fixed inset-x-0 top-0 z-40 h-[2px]"
      >
        <div className="scroll-progress h-full w-full bg-[image:var(--grad-accent)]" />
      </div>

      <Nav />
      <TierLadder />
      <Hero />
      <Ticker />
      <Boundary />
      <Rules />
      <Close />
      <Footer />
    </div>
  );
}

/* ---------------------------------------------------------------------- nav */

function Nav() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      {/* Detached and pushed left rather than centred. A pill floating dead
          centre is the same decision as a bar glued across the top, made
          slightly later. */}
      <header className="sticky top-0 z-30 flex justify-center px-4 pt-5 sm:justify-start sm:px-8">
        <nav
          aria-label="Landing"
          className="frost flex w-max items-center gap-1 rounded-full p-1.5 pl-4"
        >
          <Link
            href="/"
            className="flex items-center gap-2 pr-2 text-base font-semibold text-ink"
          >
            <Mark />
            <span className="hidden sm:inline">Extroc</span>
          </Link>

          <span aria-hidden className="mx-1 hidden h-5 w-px bg-line md:block" />

          {NAV.map((item) => (
            <a
              key={item.href}
              href={item.href}
              className="hidden rounded-full px-3 py-2 text-base text-ink-2 transition-colors duration-300 ease-out-quint hover:bg-hover hover:text-ink md:block"
            >
              {item.label}
            </a>
          ))}

          <ButtonLink
            href="/ask"
            size="sm"
            className="ml-1"
            trailing={<ArrowRightIcon size={12} weight="bold" />}
          >
            Open
          </ButtonLink>

          <button
            type="button"
            aria-label={open ? "Close menu" : "Open menu"}
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
            className="relative ml-0.5 grid size-9 cursor-pointer place-items-center rounded-full transition-colors duration-300 ease-out-quint hover:bg-hover md:hidden"
          >
            {/* Two strokes that rotate into each other, so the mark stays
                continuous through the change rather than being swapped. */}
            <span
              aria-hidden
              className={cn(
                "absolute h-px w-4 rounded-full bg-ink transition-transform duration-500 ease-out-quint",
                open ? "rotate-45" : "-translate-y-[3px]",
              )}
            />
            <span
              aria-hidden
              className={cn(
                "absolute h-px w-4 rounded-full bg-ink transition-transform duration-500 ease-out-quint",
                open ? "-rotate-45" : "translate-y-[3px]",
              )}
            />
          </button>
        </nav>
      </header>

      <div
        className={cn(
          "fixed inset-0 z-20 flex flex-col justify-center gap-2 px-8 md:hidden",
          "bg-page/85 backdrop-blur-2xl transition-opacity duration-500 ease-out-quint",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      >
        {NAV.map((item, index) => (
          <a
            key={item.href}
            href={item.href}
            onClick={() => setOpen(false)}
            style={{ transitionDelay: `${open ? 80 + index * 70 : 0}ms` }}
            className={cn(
              "macro text-2xl text-ink transition-[opacity,transform] duration-500 ease-out-quint",
              open ? "translate-y-0 opacity-100" : "translate-y-8 opacity-0",
            )}
          >
            {item.label}
          </a>
        ))}
      </div>
    </>
  );
}

function Mark() {
  const gradientId = useId();
  return (
    <svg width="20" height="20" viewBox="0 0 18 18" fill="none" aria-hidden>
      <defs>
        <linearGradient id={gradientId} x1="4" y1="3" x2="14" y2="15">
          <stop offset="0%" style={{ stopColor: "var(--brand-from)" }} />
          <stop offset="100%" style={{ stopColor: "var(--brand-to)" }} />
        </linearGradient>
      </defs>
      <circle
        cx="9"
        cy="9"
        r="7"
        stroke="var(--ink-3)"
        strokeWidth="1.5"
        strokeDasharray="2.2 2.2"
      />
      <path
        d="M9 4.6V9l3.1 2.2"
        stroke={`url(#${gradientId})`}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* --------------------------------------------------------------------- hero */

function Hero() {
  return (
    <section className="mx-auto grid w-full max-w-6xl gap-14 px-4 pt-16 pb-20 sm:px-8 sm:pt-24 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-10 lg:pt-20">
      <div>
        <Reveal>
          <p className="text-2xs font-semibold tracking-[0.2em] text-ink-3 uppercase">
            dCortex Air, Crew Control, hub BLR
          </p>
        </Reveal>

        <Reveal delay={80}>
          {/* NAMES THE PRODUCT BEFORE IT ARGUES FOR IT. The two headlines
              before this one, "The model isn't allowed to do the maths" and
              "Every figure comes with a receipt", both opened with the claim
              and never said what the product was called: a reader could sit
              through the whole hero and leave not knowing its name. A first
              screen has one job before it has any other: say who this is.
              The receipt claim survives as the second half of the sentence,
              which is what it was allowed to be replaced by, not something to
              lose. */}
          <h1 className="macro mt-5 max-w-[16ch] text-[clamp(2.5rem,5.6vw,4.25rem)] text-ink">
            Welcome to <span className="ink-gradient">Extroc</span>, where
            every figure comes with a receipt
          </h1>
        </Reveal>

        <Reveal delay={150}>
          <p className="mt-7 max-w-[58ch] text-lg leading-relaxed font-medium text-ink">
            The model plans and explains. The rules engine computes. A guard
            validates every figure before you see it.
          </p>
        </Reveal>

        <Reveal delay={210}>
          <p className="mt-4 max-w-[52ch] text-md leading-relaxed text-ink-2">
            Click any underlined number to see the deterministic trace behind
            it.
          </p>
        </Reveal>

        <Reveal delay={270}>
          <p className="mt-5 max-w-[52ch] text-md leading-relaxed text-ink-2">
            The useful consequence is that it will{" "}
            <span className="scribble font-semibold text-ink">
              tell you when it does not know
            </span>
            , which is the behaviour most of these systems get wrong.
          </p>
        </Reveal>

        <Reveal delay={330}>
          <div className="mt-9 flex flex-col gap-3 sm:flex-row">
            <ButtonLink
              href="/ask"
              size="lg"
              trailing={<ArrowUpRightIcon size={16} weight="bold" />}
            >
              Open the advisor
            </ButtonLink>
            <ButtonLink href="#boundary" variant="outline" size="lg">
              Where the line is
            </ButtonLink>
          </div>
        </Reveal>
      </div>

      {/* Three depths, not one card. The answer in front, the working behind
          it, the refusal behind that, each drifting at its own rate as the
          page moves. A single hero screenshot centred under a headline is the
          thing every one of these pages does. */}
      <div className="relative min-h-[38rem] lg:min-h-[39rem]">
        <div className="parallax-slow absolute inset-x-0 top-4 lg:top-0">
          <AnswerCard />
        </div>
        <div className="parallax-tilt absolute -right-2 bottom-10 w-[68%] max-w-[21rem] sm:right-4 lg:-right-10">
          <RefusalCard />
          <p className="mt-3 ml-auto max-w-[10rem] pr-3 text-right text-2xs leading-relaxed text-ink-3 sm:max-w-[18rem] sm:text-left">
            Ranks options heuristically, not a global optimizer: says so when
            trade-offs are close.
          </p>
        </div>
        <div className="parallax-fast absolute bottom-0 -left-2 w-[54%] max-w-[16rem] sm:left-2 lg:-left-8">
          <TraceCard />
        </div>
      </div>
    </section>
  );
}

/**
 * The worked answer.
 *
 * Every figure is real: C-1042's duty clocks, the 60h ceiling in `rules.json`,
 * and the subtraction between them. Inventing a number for the mock on the
 * landing page of a product whose entire argument is that its numbers are
 * attested would be a joke at its own expense.
 */
function AnswerCard() {
  const [mode, setMode] = useState<"lookup" | "recommendation">("lookup");

  return (
    <div className="bezel rotate-[0.6deg]">
      <div className="bezel-core overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-4 pt-3.5 pb-2">
          <div className="flex items-center gap-1.5" aria-hidden>
            <span className="size-2 rounded-full bg-line-strong" />
            <span className="size-2 rounded-full bg-line-strong" />
            <span className="size-2 rounded-full bg-line-strong" />
          </div>
          <div
            className="flex rounded-full bg-inset p-1"
            aria-label="Answer depth"
            role="tablist"
          >
            <button
              type="button"
              role="tab"
              aria-selected={mode === "lookup"}
              onClick={() => setMode("lookup")}
              className={cn(
                "cursor-pointer rounded-full px-3 py-1 text-2xs font-semibold transition-[background-color,color,box-shadow] duration-300 ease-out-quint",
                mode === "lookup"
                  ? "bg-surface text-ink shadow-panel"
                  : "text-ink-3 hover:text-ink",
              )}
            >
              Lookup
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "recommendation"}
              onClick={() => setMode("recommendation")}
              className={cn(
                "cursor-pointer rounded-full px-3 py-1 text-2xs font-semibold transition-[background-color,color,box-shadow] duration-300 ease-out-quint",
                mode === "recommendation"
                  ? "bg-surface text-ink shadow-panel"
                  : "text-ink-3 hover:text-ink",
              )}
            >
              Recommendation
            </button>
          </div>
        </div>
        <div role="tabpanel" aria-label={`${mode} answer`}>
          {mode === "lookup" ? <LookupAnswer /> : <RecommendationAnswer />}
        </div>
      </div>
    </div>
  );
}

function LookupAnswer() {
  return (
    <div className="px-5 pb-5">
      <div className="flex justify-end">
        <p
          className="max-w-[30ch] rounded-2xl px-3.5 py-2 text-base text-[var(--voice-ink)]"
          style={{ backgroundImage: "var(--grad-voice)" }}
        >
          How much duty headroom does C-1042 have?
        </p>
      </div>
      <p className="mt-4 text-base leading-relaxed text-ink">
        C-1042 has accrued <Atom trace="get_duty_clocks">20.93</Atom> duty
        hours in the 7 calendar days ending 2026-09-14, leaving{" "}
        <Atom trace="get_duty_clocks → explain_rule">39.07h</Atom> of headroom
        under <Atom trace="explain_rule">RULE-DUTY-02</Atom>, whose limit is{" "}
        <Atom trace="explain_rule">60h</Atom>.
      </p>
      <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-pass-tint px-2.5 py-1 text-2xs font-semibold text-pass">
        <CheckCircleIcon size={11} weight="fill" aria-hidden />
        12 of 12 figures attested
      </span>
    </div>
  );
}

const HERO_OPTIONS = [
  {
    rank: "01",
    crew: "C-3310",
    cost: "INR 18,500",
    reason: "Reserve callout, covers both days with no delay.",
  },
  {
    rank: "02",
    crew: "C-1526",
    cost: "INR 24,000",
    reason: "Day-off callout, covers both days with no delay.",
  },
  {
    rank: "03",
    crew: "C-3983",
    cost: "INR 24,000",
    reason: "Day-off callout, covers both days with no delay.",
  },
] as const;

function RecommendationAnswer() {
  return (
    <div className="px-5 pb-5">
      <div className="flex justify-end">
        <p
          className="max-w-[34ch] rounded-2xl px-3.5 py-2 text-base text-[var(--voice-ink)]"
          style={{ backgroundImage: "var(--grad-voice)" }}
        >
          Best way to cover P-2291?
        </p>
      </div>
      <div className="mt-4 flex items-center justify-between gap-3">
        <p className="text-base font-semibold text-ink">Ranked legal options</p>
        <p className="text-2xs text-ink-3">All 7 rules checked</p>
      </div>
      <ol className="mt-2 grid gap-1.5">
        {HERO_OPTIONS.map((option) => (
          <li
            key={option.crew}
            className="grid grid-cols-[1.5rem_1fr_auto] items-start gap-x-2 rounded-xl bg-inset px-3 py-2.5"
          >
            <span className="num pt-0.5 text-2xs text-ink-3">
              {option.rank}
            </span>
            <span className="min-w-0">
              <span className="num text-xs font-semibold text-ink">
                {option.crew}
              </span>
              <span className="mt-0.5 block text-2xs leading-snug text-ink-2">
                {option.reason}
              </span>
            </span>
            <span className="text-right">
              <span className="num block text-2xs font-semibold text-ink">
                {option.cost}
              </span>
              <span className="mt-1 inline-flex rounded-full bg-pass-tint px-2 py-0.5 text-[10px] font-semibold text-pass">
                Legal
              </span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function TraceCard() {
  return (
    <div className="bezel -rotate-[1.6deg]">
      <div className="bezel-core p-4">
        <p className="text-2xs font-semibold tracking-[0.16em] text-ink-3 uppercase">
          How it got there
        </p>
        <ol className="mt-2.5 grid gap-1.5">
          {["get_crew_detail", "get_duty_clocks", "explain_rule"].map(
            (tool, index) => (
              <li key={tool} className="flex items-center gap-2">
                <span className="num w-3 text-2xs text-ink-3">{index + 1}</span>
                <span className="mono truncate text-2xs text-ink-2">{tool}</span>
                <CheckCircleIcon
                  size={11}
                  weight="fill"
                  aria-hidden
                  className="ml-auto shrink-0 text-pass"
                />
              </li>
            ),
          )}
        </ol>
      </div>
    </div>
  );
}

function RefusalCard() {
  return (
    <div className="bezel rotate-[2.2deg]">
      <div className="bezel-core p-4">
        <p className="text-base font-semibold text-ink">No answer given</p>
        <p className="mt-1.5 text-xs leading-relaxed text-ink-2">
          I cannot answer that reliably. The question is about weather, which
          this dataset does not model.
        </p>
        <p className="mt-2.5 text-2xs text-ink-3">
          A refusal is a result, and it is rendered as one.
        </p>
      </div>
    </div>
  );
}

function Atom({
  children,
  trace,
}: {
  children: React.ReactNode;
  trace: string;
}) {
  const [open, setOpen] = useState(false);

  return (
    <span className="group/atom relative inline-block">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="num cursor-pointer rounded-xs bg-accent-tint px-0.5 text-accent underline decoration-dotted decoration-1 underline-offset-[3px] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
      >
        {children}
      </button>
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute bottom-[calc(100%+0.45rem)] left-1/2 z-10 w-max max-w-[14rem] -translate-x-1/2 rounded-lg bg-ink px-2.5 py-1.5 text-center font-mono text-[10px] leading-snug text-page shadow-pop transition-[opacity,transform] duration-200",
          open
            ? "translate-y-0 opacity-100"
            : "translate-y-1 opacity-0 group-hover/atom:translate-y-0 group-hover/atom:opacity-100 group-focus-within/atom:translate-y-0 group-focus-within/atom:opacity-100",
        )}
      >
        {trace}
      </span>
    </span>
  );
}

/* ------------------------------------------------------------------- ticker */

function Ticker() {
  return (
    <div
      aria-hidden
      className="relative flex overflow-hidden border-y border-line-soft py-4"
    >
      {/* Rendered twice so the loop has something to arrive at. Hover pauses
          it, because a reader who stops to look at a moving list and cannot
          read it is being shown a decoration, not a fact. */}
      <div className="marquee">
        {[0, 1].map((copy) => (
          <div key={copy} className="flex shrink-0 items-center">
            {TICKER.map((item) => (
              <span key={item} className="flex items-center">
                <span className="num px-6 text-base whitespace-nowrap text-ink-2">
                  {item}
                </span>
                <span className="size-1 shrink-0 rounded-full bg-line-strong" />
              </span>
            ))}
          </div>
        ))}
      </div>
      <span className="sr-only">
        The dataset: 147 flights, 150 crew, 39 pairings, 16 reserves, 7 rules, 6
        worked scenarios and 38 questions with answer keys. The cheapest legal
        option is found in under 2 seconds. The data covers one week, all times
        UTC.
      </span>
    </div>
  );
}

/* --------------------------------------------------------------- tier ladder */

function TierLadder() {
  const [selected, setSelected] = useState<Capability | null>(null);

  return (
    <>
      <section
        id="work"
        className="mx-auto w-full max-w-6xl scroll-mt-24 px-4 pt-16 pb-24 sm:px-8 sm:pt-20 sm:pb-32"
      >
        <Reveal>
          <p className="text-2xs font-semibold tracking-[0.2em] text-ink-3 uppercase">
            Three levels of answer
          </p>
          <h2 className="macro mt-4 text-[clamp(2rem,4vw,3.25rem)] text-ink">
            Lookup <span className="text-accent">→</span> Consequence{" "}
            <span className="text-accent">→</span> Recommendation
          </h2>
        </Reveal>

        <div className="mt-12 grid gap-4 lg:grid-cols-3 lg:items-start">
          {TIER_LADDER.map((tier, index) => (
            <Reveal
              key={tier.name}
              delay={index * 90}
              className={cn(index === 1 && "lg:mt-8", index === 2 && "lg:mt-16")}
            >
              <article
                className="rounded-[2rem] p-6 shadow-panel sm:p-7"
                style={{ background: `var(--tint-${tier.tint})` }}
              >
                <div className="flex items-center justify-between gap-4">
                  <p
                    className="num text-2xs font-semibold tracking-[0.16em] uppercase"
                    style={{ color: `var(--tint-${tier.tint}-ink)` }}
                  >
                    Tier {tier.n}
                  </p>
                  <span
                    aria-hidden
                    className="grid size-8 place-items-center rounded-full text-page"
                    style={{ background: `var(--tint-${tier.tint}-ink)` }}
                  >
                    {index + 1}
                  </span>
                </div>
                <h3 className="macro mt-5 text-2xl text-ink">{tier.name}</h3>
                <p className="mt-2 text-base leading-relaxed text-ink-2">
                  {tier.definition}
                </p>
                <div className="mt-6 grid gap-2">
                  {tier.capabilities.map((capability) => (
                    <button
                      key={capability.id}
                      type="button"
                      onClick={() => setSelected(capability)}
                      data-testid="capability-card"
                      className="group flex min-h-24 cursor-pointer items-center gap-3 rounded-2xl bg-surface/75 px-4 py-3 text-left text-sm leading-snug text-ink shadow-[var(--ring-faint)] transition-[transform,box-shadow,background-color] duration-300 ease-out-quint hover:-translate-y-0.5 hover:bg-surface hover:shadow-panel focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block text-base font-semibold text-ink">
                          {capability.label}
                        </span>
                        <span className="mt-1 block text-xs leading-snug text-ink-2">
                          {capability.description}
                        </span>
                      </span>
                      <ArrowUpRightIcon
                        size={13}
                        weight="bold"
                        aria-hidden
                        className="shrink-0 text-ink-3 transition-transform duration-300 ease-out-quint group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                      />
                    </button>
                  ))}
                </div>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      {selected ? (
        <CapabilityLauncher
          key={selected.id}
          capability={selected}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </>
  );
}

function CapabilityLauncher({
  capability,
  onClose,
}: {
  capability: Capability;
  onClose: () => void;
}) {
  const [values, setValues] = useState<CapabilityValues>({});
  const complete = capability.fields.every((field) => values[field.key]?.trim());
  const question = complete ? capability.buildQuestion(values) : "";

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center px-4 py-8">
      <button
        type="button"
        aria-label="Close task details"
        onClick={onClose}
        className="absolute inset-0 cursor-default bg-ink/25 backdrop-blur-sm"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={`capability-${capability.id}`}
        className="relative max-h-[calc(100dvh-2rem)] w-full max-w-lg overflow-y-auto rounded-[2rem] bg-surface p-6 shadow-pop sm:p-8"
      >
        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="text-2xs font-semibold tracking-[0.18em] text-accent uppercase">
              Start with the facts
            </p>
            <h3
              id={`capability-${capability.id}`}
              className="macro mt-2 text-2xl text-ink"
            >
              {capability.label}
            </h3>
            <p className="mt-2 text-base leading-relaxed text-ink-2">
              {capability.description}
            </p>
          </div>
          <button
            type="button"
            aria-label="Close task details"
            onClick={onClose}
            className="grid size-9 shrink-0 cursor-pointer place-items-center rounded-full bg-inset text-lg text-ink-2 transition-colors duration-200 hover:bg-hover hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          >
            <span aria-hidden>×</span>
          </button>
        </div>

        <form action="/ask" method="get" className="mt-7">
          <input type="hidden" name="q" value={question} />
          <div className="grid gap-4 sm:grid-cols-2">
            {capability.fields.map((field, index) => (
              <label
                key={field.key}
                className={cn(
                  "grid gap-1.5 text-xs font-semibold text-ink-2",
                  capability.fields.length % 2 === 1 &&
                    index === capability.fields.length - 1 &&
                    "sm:col-span-2",
                )}
              >
                {field.label}
                <input
                  autoFocus={index === 0}
                  required
                  type={field.type ?? "text"}
                  placeholder={field.placeholder}
                  value={values[field.key] ?? ""}
                  onChange={(event) =>
                    setValues((current) => ({
                      ...current,
                      [field.key]: event.target.value,
                    }))
                  }
                  className="h-12 min-w-0 rounded-xl bg-inset px-3.5 text-base font-medium text-ink shadow-[inset_0_0_0_1px_var(--line-soft)] outline-none transition-[background-color,box-shadow] duration-200 placeholder:text-ink-3 focus:bg-surface focus:shadow-[inset_0_0_0_2px_var(--accent-line)]"
                />
              </label>
            ))}
          </div>

          <div className="mt-6 rounded-2xl bg-inset px-4 py-3">
            <p className="text-2xs font-semibold tracking-[0.14em] text-ink-3 uppercase">
              Opens chat with
            </p>
            <p className="mt-1.5 min-h-[2.5rem] text-sm leading-relaxed text-ink-2">
              {question || "Enter the details above to build the question."}
            </p>
          </div>

          <div className="mt-6 flex justify-end">
            <Button
              type="submit"
              size="md"
              disabled={!complete}
              trailing={<ArrowRightIcon size={13} weight="bold" />}
            >
              Continue to chat
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- boundary */

function Boundary() {
  return (
    <section
      id="boundary"
      className="mx-auto w-full max-w-6xl scroll-mt-24 px-4 py-32 sm:px-8 sm:py-48"
    >
      <div className="grid gap-12 lg:grid-cols-[0.9fr_1.1fr] lg:gap-16">
        <Reveal>
          {/* The heading sits still on the left while the two lists scroll
              past it, which is what the sticky is for. */}
          <div className="lg:sticky lg:top-28">
            <p className="text-2xs font-semibold tracking-[0.2em] text-ink-3 uppercase">
              Where the line is
            </p>
            <h2 className="macro mt-5 max-w-[14ch] text-[clamp(2rem,4vw,3.25rem)] text-ink">
              <Words text="One of these lists is the whole product" />
            </h2>
            <p className="mt-6 max-w-[46ch] text-md leading-relaxed text-ink-2">
              Legality is exact arithmetic against a rulebook. A model that
              approximates a duty hour calculation gives you an answer that is
              fluent, confident and wrong, which on a crew desk is worse than no
              answer at all.
            </p>
            <p className="mt-4 max-w-[46ch] text-md leading-relaxed text-ink-2">
              So it is not a line in a prompt asking nicely. It is a node in the
              graph that can throw the turn away, and there is a test that fails
              the build if a model client is ever importable from the packages
              that compute.
            </p>
          </div>
        </Reveal>

        <div className="grid gap-4">
          <div className="settle">
            <List tone="pass" title="It may" items={MAY} />
          </div>
          <div className="settle-alt">
            <List tone="breach" title="It may not" items={MAY_NOT} />
          </div>
          <Reveal delay={200}>
            <div className="rounded-[2rem] bg-ink px-7 py-8 text-page sm:px-9">
              <p className="macro text-xl">And then something checks</p>
              <p className="mt-3.5 max-w-[52ch] text-base leading-relaxed opacity-80">
                The draft is pulled apart into atoms: numbers, crew ids, rule
                ids, station codes, dates. Each one has to match a fact a tool
                returned. One that does not fails the turn, and the turn is
                rewritten or refused.
              </p>
              <p className="mt-3.5 max-w-[52ch] text-base leading-relaxed opacity-80">
                A prompt telling a model not to invent figures is a request. A
                node that can reject the answer is a constraint. Only one of
                those survives contact with a model having a bad day.
              </p>
            </div>
          </Reveal>
        </div>
      </div>
    </section>
  );
}

function List({
  tone,
  title,
  items,
}: {
  tone: "pass" | "breach";
  title: string;
  items: string[];
}) {
  return (
    <div className="bezel">
      <div className="bezel-core p-7 sm:p-8">
        <div className="flex items-baseline gap-2.5">
          <span
            aria-hidden
            className={cn(
              "size-2 rounded-full",
              tone === "pass" ? "bg-pass" : "bg-breach",
            )}
          />
          <h3 className="macro text-xl text-ink">{title}</h3>
        </div>
        <ul className="mt-5 grid gap-3.5">
          {items.map((item, index) => (
            <li key={item} className="flex gap-3.5">
              <span className="num w-4 shrink-0 pt-0.5 text-2xs text-ink-3">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="text-base leading-relaxed text-ink-2">{item}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- rules */

function Rules() {
  return (
    <section
      id="rules"
      className="mx-auto w-full max-w-6xl scroll-mt-24 px-4 py-32 sm:px-8 sm:py-48"
    >
      <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
        <Reveal>
          <div className="lg:sticky lg:top-28">
            <p className="text-2xs font-semibold tracking-[0.2em] text-ink-3 uppercase">
              Seven, and there is no eighth
            </p>
            <h2 className="macro mt-5 max-w-[12ch] text-[clamp(2rem,4vw,3.25rem)] text-ink">
              <Words text="The rulebook, as shipped" />
            </h2>
            <p className="mt-6 max-w-[42ch] text-md leading-relaxed text-ink-2">
              Every candidate for every cover is checked against all seven, on
              every day of the assignment. Legal on day one and breaching on day
              two is not a legal option.
            </p>
            <p className="mt-4 max-w-[42ch] text-md leading-relaxed text-ink-2">
              Ask it about an eighth and it will tell you there isn&rsquo;t one.
            </p>
          </div>
        </Reveal>

        <Reveal delay={120}>
          <Accordion type="single" collapsible className="grid gap-1.5">
            {RULES.map((rule, index) => (
              <AccordionItem key={rule.id} value={rule.id}>
                <AccordionTrigger>
                  <span className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span
                      className="num text-2xs font-semibold"
                      style={{ color: `var(--tint-${(index % 6) + 1}-ink)` }}
                    >
                      {rule.id}
                    </span>
                    <span className="text-md font-medium text-ink">
                      {rule.title}
                    </span>
                    <span className="num rounded-full bg-inset px-2 py-0.5 text-2xs text-ink-2">
                      {rule.limit}
                    </span>
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <p className="max-w-[62ch] text-base leading-relaxed text-ink">
                    {rule.constraint}
                  </p>
                  <p className="mt-2.5 max-w-[62ch] text-base leading-relaxed text-ink-2">
                    {rule.note}
                  </p>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </Reveal>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------- close */

function Close() {
  return (
    <section className="mx-auto w-full max-w-6xl px-4 pb-24 sm:px-8 sm:pb-32">
      <Reveal>
        <div className="relative overflow-hidden rounded-[2.5rem] bg-ink px-7 py-20 sm:px-14 sm:py-24">
          <div
            aria-hidden
            className="parallax-slow pointer-events-none absolute -inset-x-20 -top-40 h-[36rem] opacity-40"
            style={{ backgroundImage: "var(--grad-hero)" }}
          />
          {/* The measure goes on the heading, not on this wrapper. `ch` is
              relative to the element's OWN font size, so `max-w-[24ch]` here
              resolved against 17px body text and clamped a 56px headline to
              about 200px, which broke it after "ask it". */}
          <div className="relative">
            <h2 className="macro max-w-[15ch] text-[clamp(2rem,4.5vw,3.5rem)] text-page">
              <Words text="Go on, ask it something it cannot answer" />
            </h2>
            <p className="mt-6 max-w-[48ch] text-md leading-relaxed text-page/70">
              That is the part worth checking first. Everything else any of
              these systems can fake.
            </p>
            <div className="mt-10 flex flex-col gap-3 sm:flex-row">
              <ButtonLink
                href="/ask"
                variant="secondary"
                size="lg"
                trailing={<ArrowUpRightIcon size={16} weight="bold" />}
              >
                Open the advisor
              </ButtonLink>
              <ButtonLink
                href="/architecture"
                variant="ghost"
                size="lg"
                className="bg-page/10 text-page hover:bg-page/20 hover:text-page"
              >
                Read the architecture
              </ButtonLink>
            </div>
          </div>
        </div>
      </Reveal>

    </section>
  );
}

/* ------------------------------------------------------------------- footer */

const FOOTER_LINKS = [
  {
    heading: "The product",
    links: [
      { href: "/ask", label: "Ask it something" },
      { href: "/brief", label: "The morning brief" },
      { href: "/ops", label: "The rules engine" },
      { href: "/architecture", label: "Where the line is" },
    ],
  },
  {
    heading: "Try these",
    links: [
      {
        href: "/ask?q=Who%20is%20on%20reserve%20at%20BLR%20on%202026-09-15%3F",
        label: "Reserves at BLR",
      },
      {
        href: "/ask?q=Captain%20C-1042%20calls%20in%20sick%20on%2015%20Sep.%20Which%20flights%20are%20uncrewed%3F",
        label: "A captain calls in sick",
      },
      {
        href: "/ask?q=C-1042%20is%20out%20for%20P-2291.%20Produce%20ranked%20options%20with%20costs.",
        label: "Rank me some options",
      },
      {
        href: "/ask?q=Is%20the%20weather%20going%20to%20delay%20DX401%20on%2016%20Sep%3F",
        label: "Something it refuses",
      },
    ],
  },
  {
    heading: "The dataset",
    links: [
      { href: "/ops", label: "147 flights, 150 crew" },
      { href: "/ops", label: "39 pairings, 16 reserves" },
      { href: "/ops", label: "7 rules, and no eighth" },
      { href: "/ops", label: "38 questions with keys" },
    ],
  },
];

/** The second ticker, running the other way, so the page closes on a rhyme. */
const FOOTER_TICKER = [
  "the model plans",
  "the code computes",
  "the guard checks",
  "and if it cannot, it says so",
];

function Footer() {
  return (
    <footer className="relative mt-8 overflow-hidden">
      <div className="border-y border-line-soft py-3.5">
        <div className="marquee-reverse" aria-hidden>
          {[0, 1].map((copy) => (
            <div key={copy} className="flex shrink-0 items-center">
              {FOOTER_TICKER.map((item) => (
                <span key={item} className="flex items-center">
                  <span className="px-6 text-base whitespace-nowrap text-ink-3">
                    {item}
                  </span>
                  <span className="size-1 shrink-0 rounded-full bg-line-strong" />
                </span>
              ))}
            </div>
          ))}
        </div>
      </div>

      <div className="mx-auto w-full max-w-6xl px-4 pt-16 sm:px-8">
        <div className="grid gap-12 lg:grid-cols-[1fr_1.5fr]">
          <Reveal>
            <div>
              <div className="flex items-center gap-2.5">
                <Mark />
                <p className="text-md font-semibold text-ink">Extroc</p>
              </div>
              <p className="mt-5 max-w-[34ch] text-base leading-relaxed text-ink-2">
                A decision aid for the dCortex Air Crew Control desk. One week
                of a real network, seven rules, and an answer you are meant to
                argue with rather than take on trust.
              </p>
              <p className="num mt-5 text-xs text-ink-3">
                Snapshot 2026-09-14T18:00:00Z. All times UTC, currency INR.
              </p>
            </div>
          </Reveal>

          <div className="grid gap-8 sm:grid-cols-3">
            {FOOTER_LINKS.map((column, index) => (
              <Reveal key={column.heading} delay={index * 90}>
                <p className="text-2xs font-semibold tracking-[0.18em] text-ink-3 uppercase">
                  {column.heading}
                </p>
                <ul className="mt-4 grid gap-2.5">
                  {column.links.map((link) => (
                    <li key={link.label}>
                      <Link
                        href={link.href}
                        className="group inline-flex items-center gap-1.5 text-base text-ink-2 transition-colors duration-300 ease-out-quint hover:text-ink"
                      >
                        {link.label}
                        <ArrowUpRightIcon
                          size={11}
                          weight="bold"
                          aria-hidden
                          className="translate-y-px opacity-0 transition-[opacity,transform] duration-300 ease-out-quint group-hover:translate-x-0.5 group-hover:opacity-100"
                        />
                      </Link>
                    </li>
                  ))}
                </ul>
              </Reveal>
            ))}
          </div>
        </div>

        <p className="macro mt-16 max-w-[52ch] text-base text-ink-2">
          The advisor a controller wants beside them at 6am on a bad day.
        </p>
        <p className="mt-5 flex flex-wrap items-center gap-x-2 gap-y-1 pb-6 text-xs text-ink-3">
          Built for the dCortex Agentic Crew Ops Advisor problem statement.
          <span aria-hidden>&middot;</span>
          <span>
            The dataset is read only, and the answer keys are the ones it
            shipped with.
          </span>
        </p>
      </div>

      {/* THE WORDMARK IS THE FLOOR OF THE PAGE, and now it is a plinth the
          page stands on rather than a watermark bled into it. At six percent
          of the ink colour on the page's own cream it read as a printing
          fault, something that had failed to load; the name of the product
          should not be the faintest thing on its own landing page. Dropped
          onto a dark band it is simply the end of the document, which is
          what the shape was always trying to say.

          Still cropped by the bottom edge on purpose, still drifting
          sideways against the scroll, still `aria-hidden`, because it is
          furniture rather than a heading and the accessible name of this
          page is set four times above it.

          `overflow-hidden` on this wrapper is load bearing rather than tidy:
          the type size was raised for the shorter name (six letters against
          "crew ops advisor"'s sixteen) without raising the box that holds
          it, so the glyphs stood taller than their container and spilled
          upward into the link columns and the credit line above. Clipping to
          the wrapper is what turns "escaped text" back into "a wordmark
          cropped on purpose", regardless of how the two numbers are tuned. */}
      <div
        aria-hidden
        className="pointer-events-none relative mt-6 h-[11vw] min-h-[4rem] overflow-hidden bg-ink select-none"
      >
        <p className="drift-left macro absolute inset-x-0 -bottom-[2vw] text-center text-[16vw] leading-none whitespace-nowrap text-page opacity-90">
          Extroc
        </p>
      </div>
    </footer>
  );
}
