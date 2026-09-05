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
  DatabaseIcon,
  ScalesIcon,
  TreeStructureIcon,
} from "@phosphor-icons/react/dist/ssr";

import { Reveal, revealClasses, useInView } from "@/components/landing/reveal";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { ButtonLink } from "@/components/ui/button";
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

const TIERS = [
  {
    n: "01",
    name: "Look it up",
    tint: 1,
    icon: DatabaseIcon,
    blurb:
      "Who is on reserve at BLR. What a crew member's duty clocks read. Which flights leave DEL on Tuesday. Straight out of the dataset, with the file and the record named underneath so you can go and check.",
    example: "Who is on reserve at BLR on 2026-09-15?",
  },
  {
    n: "02",
    name: "Work out what breaks",
    tint: 2,
    icon: TreeStructureIcon,
    blurb:
      "A captain calls in sick at five in the morning. A station shuts for six hours. An aircraft is ninety minutes late. Which legs lose their crew, what that reaches next, and which limit the delay quietly pushes somebody over.",
    example: "Captain C-1042 calls in sick on 15 Sep. Which flights are uncrewed?",
  },
  {
    n: "03",
    name: "Argue for an option",
    tint: 4,
    icon: ScalesIcon,
    blurb:
      "Every candidate found, checked against all seven rules on every day of the cover, priced, ranked. The ones that did not make it are shown too, each with the rule that knocked it out, because a search you cannot see the shape of is indistinguishable from a guess.",
    example: "C-1042 is out for P-2291. Produce ranked options with costs.",
  },
] as const;

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
      <Hero />
      <Ticker />
      <Boundary />
      <Work />
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
          <p className="mt-7 max-w-[52ch] text-md leading-relaxed text-ink-2">
            The model plans the work and writes the explanation, which is what
            a language model is genuinely good at. The arithmetic belongs to
            deterministic code, and a guard reads the draft back against the
            tool results before anybody sees it. Click any number in an answer
            and it will show you the file, the record and the subtraction.
          </p>
        </Reveal>

        <Reveal delay={220}>
          <p className="mt-5 max-w-[52ch] text-md leading-relaxed text-ink-2">
            The useful consequence is that it will{" "}
            <span className="scribble font-semibold text-ink">
              tell you when it does not know
            </span>
            , which is the behaviour most of these systems get wrong.
          </p>
        </Reveal>

        <Reveal delay={290}>
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
      <div className="relative min-h-[26rem] lg:min-h-[34rem]">
        <div className="parallax-slow absolute inset-x-0 top-4 lg:top-0">
          <AnswerCard />
        </div>
        <div className="parallax-tilt absolute -right-2 bottom-8 w-[62%] max-w-[19rem] sm:right-4 lg:-right-10">
          <RefusalCard />
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
  return (
    <div className="bezel rotate-[0.6deg]">
      <div className="bezel-core overflow-hidden">
        <div className="flex items-center gap-1.5 px-4 pt-3.5 pb-2">
          <span className="size-2 rounded-full bg-line-strong" />
          <span className="size-2 rounded-full bg-line-strong" />
          <span className="size-2 rounded-full bg-line-strong" />
        </div>
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
            C-1042 has accrued <Atom>20.93</Atom> duty hours in the 7 calendar
            days ending 2026-09-14, leaving <Atom>39.07h</Atom> of headroom
            under <Atom>RULE-DUTY-02</Atom>, whose limit is <Atom>60h</Atom>.
          </p>
          <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-pass-tint px-2.5 py-1 text-2xs font-semibold text-pass">
            <CheckCircleIcon size={11} weight="fill" aria-hidden />
            12 of 12 figures attested
          </span>
        </div>
      </div>
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

function Atom({ children }: { children: React.ReactNode }) {
  return (
    <span className="num rounded-xs bg-accent-tint px-0.5 text-accent underline decoration-dotted decoration-1 underline-offset-[3px]">
      {children}
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
        worked scenarios and 38 questions with answer keys, over one week, all
        times UTC.
      </span>
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

/* --------------------------------------------------------------------- work */

/**
 * The horizontal section.
 *
 * The reader scrolls down and the cards walk left. It is a CSS scroll
 * timeline, so the whole thing runs on the compositor and there is no scroll
 * handler anywhere; where scroll timelines are not supported the same markup
 * degrades to a row you swipe, which is the reason the track is a real
 * overflow container in the base stylesheet rather than a transform.
 */
function Work() {
  return (
    <section id="work" className="scroll-mt-0">
      <div className="hscroll">
        <div className="hscroll-pin relative">
          {/* THE HEADING LIVES INSIDE THE PIN. It used to sit above the
              section, which meant it had scrolled off the top before the
              cards started moving: the reader arrived at a screen of cards
              with no label, scrolled, and could not tell whether the sideways
              movement was the page doing something or a rendering glitch.
              Kept on screen for the whole pin, the horizontal walk is
              obviously the answer to the scroll. */}
          <div className="mx-auto w-full max-w-6xl shrink-0 px-4 pt-24 pb-8 sm:px-8">
            <div>
              <p className="text-2xs font-semibold tracking-[0.2em] text-ink-3 uppercase">
                Three kinds of question
              </p>
              <h2 className="macro mt-4 max-w-[16ch] text-[clamp(1.75rem,3.4vw,2.75rem)] text-ink">
                <Words text="It goes as far as the question does" />
              </h2>
            </div>
          </div>

          <div className="hscroll-scroller flex min-h-0 flex-1 items-center">
            <div className="hscroll-track">
              {TIERS.map((tier) => (
                <WorkCard key={tier.n} {...tier} />
              ))}
              <FourthCard />
            </div>
          </div>

          <div className="mx-auto w-full max-w-6xl shrink-0 px-4 pt-6 pb-12 sm:px-8">
            <div aria-hidden className="h-px bg-line">
              <div className="hscroll-progress h-px w-full bg-[image:var(--grad-accent)]" />
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function WorkCard({
  n,
  name,
  tint,
  icon: Icon,
  blurb,
  example,
}: (typeof TIERS)[number]) {
  return (
    <Link
      href={`/ask?q=${encodeURIComponent(example)}`}
      style={{ background: `var(--tint-${tint})` }}
      className="group flex min-h-[24rem] w-[82vw] max-w-[30rem] shrink-0 flex-col rounded-[2rem] p-8 transition-[transform,box-shadow] duration-500 ease-out-quint hover:-translate-y-1 hover:shadow-pop sm:min-h-[30rem] sm:w-[62vw] sm:p-10"
    >
      <div className="flex items-center justify-between">
        <span
          className="macro text-5xl opacity-30"
          style={{ color: `var(--tint-${tint}-ink)` }}
        >
          {n}
        </span>
        <span
          className="grid size-11 place-items-center rounded-2xl"
          style={{
            background: `var(--tint-${tint}-tile)`,
            color: `var(--tint-${tint}-ink)`,
          }}
        >
          <Icon size={20} weight="regular" />
        </span>
      </div>

      <h3 className="macro mt-8 text-3xl text-ink">{name}</h3>
      <p className="mt-4 max-w-[42ch] text-md leading-relaxed text-ink-2">
        {blurb}
      </p>

      <p className="mt-auto flex items-center gap-3 pt-8 text-base font-medium text-ink">
        <span className="min-w-0 flex-1">{example}</span>
        <span
          aria-hidden
          className="grid size-9 shrink-0 place-items-center rounded-full text-page transition-transform duration-500 ease-out-quint group-hover:translate-x-1"
          style={{ background: `var(--tint-${tint}-ink)` }}
        >
          <ArrowRightIcon size={14} weight="bold" />
        </span>
      </p>
    </Link>
  );
}

/** The one at the end of the track, which is the point of the other three. */
function FourthCard() {
  return (
    <div className="flex min-h-[24rem] w-[82vw] max-w-[30rem] shrink-0 flex-col justify-center rounded-[2rem] bg-ink p-8 text-page sm:min-h-[30rem] sm:w-[52vw] sm:p-10">
      <p className="text-2xs font-semibold tracking-[0.2em] uppercase opacity-60">
        And the fourth kind
      </p>
      <h3 className="macro mt-5 text-3xl">The one it refuses</h3>
      <p className="mt-4 max-w-[38ch] text-md leading-relaxed opacity-80">
        Ask it about the weather, or about a crew member who is not in the
        dataset, or about a rule nobody wrote down. It will tell you what it was
        missing instead of finding you something that sounds right.
      </p>
      <div className="mt-8">
        <ButtonLink
          href="/ask?q=Is%20the%20weather%20going%20to%20delay%20DX401%20on%2016%20Sep%3F"
          variant="secondary"
          size="md"
          trailing={<ArrowRightIcon size={13} weight="bold" />}
        >
          Try to break it
        </ButtonLink>
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

        <p className="mt-16 flex flex-wrap items-center gap-x-2 gap-y-1 pb-6 text-xs text-ink-3">
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
