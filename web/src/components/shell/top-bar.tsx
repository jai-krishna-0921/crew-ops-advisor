"use client";

/**
 * The console header.
 *
 * Carries the two things a controller needs to know before they trust
 * anything on screen: which dataset snapshot they are looking at, and whether
 * the agent or the deterministic resolver is answering. Neither is hidden
 * behind a menu, because hiding the mode would overstate the system.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { MagnifyingGlassIcon } from "@phosphor-icons/react/dist/ssr";

import type { HealthResponse } from "@/lib/contracts";
import { api, USE_MOCKS } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { Kbd, Pill } from "@/components/ui/primitives";
import { cx } from "@/components/ui/tone";

const NAV = [
  { href: "/", label: "Advisor" },
  { href: "/brief", label: "Brief" },
  { href: "/ops", label: "Operations" },
  { href: "/architecture", label: "Architecture" },
] as const;

export function TopBar({ onOpenPalette }: { onOpenPalette?: () => void }) {
  const pathname = usePathname();
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .health()
      .then((value) => {
        if (!cancelled) setHealth(value);
      })
      .catch(() => {
        if (!cancelled) setHealth(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-canvas px-3 sm:px-4">
      <Link href="/" className="flex shrink-0 items-center gap-2">
        <Mark />
        <span className="hidden text-base font-semibold tracking-tight text-ink sm:inline">
          Crew Ops Advisor
        </span>
      </Link>

      <nav aria-label="Sections" className="flex items-center gap-0.5">
        {NAV.map((item) => {
          const active =
            item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "rounded-sm px-2 py-1 text-base transition-colors duration-100",
                active
                  ? "bg-inset text-ink hairline"
                  : "text-ink-3 hover:bg-hover hover:text-ink-2",
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="ml-auto flex items-center gap-2">
        {onOpenPalette ? (
          <button
            type="button"
            onClick={onOpenPalette}
            className="hidden items-center gap-1.5 rounded-sm bg-inset px-2 py-1 text-xs text-ink-3 ring-1 ring-line transition-colors duration-100 hover:text-ink-2 md:inline-flex"
          >
            <MagnifyingGlassIcon size={11} weight="bold" aria-hidden />
            Search
            <Kbd>⌘K</Kbd>
          </button>
        ) : null}

        {health ? (
          <span
            className="num hidden text-xs text-ink-3 lg:inline"
            title="Dataset snapshot. All times UTC."
          >
            {dateTime(health.snapshot)}Z
          </span>
        ) : null}

        <Pill
          tone={health?.llm_configured ? "accent" : "na"}
          title={
            health?.llm_configured
              ? "An API key is configured, so the LangGraph agent plans each turn."
              : "No API key configured. The deterministic resolver answers, using the same tools and the same guard."
          }
        >
          {health ? (health.llm_configured ? "Agent" : "Deterministic") : "Connecting"}
        </Pill>

        {USE_MOCKS ? (
          <Pill tone="caution" title="NEXT_PUBLIC_USE_MOCKS=1. Fixture data, no API.">
            Mock data
          </Pill>
        ) : null}

        <ThemeToggle />
      </div>
    </header>
  );
}

/**
 * The mark: a duty clock at the limit. Two strokes, no wordmark inside, so it
 * reads at 16px in a browser tab as easily as in the header.
 */
function Mark() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 18 18"
      fill="none"
      aria-hidden
      className="shrink-0"
    >
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
        stroke="var(--accent)"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
