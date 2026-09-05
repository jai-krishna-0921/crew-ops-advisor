"use client";

/**
 * The section rail: four destinations, down the right edge.
 *
 * IT MOVED OFF THE TOP. A full-width header cut a horizontal line across every
 * page and turned the content under it into a second box, which is the most
 * reliable way to make a product look like an admin template. Vertically, the
 * same four links cost 56px of a very wide axis instead of 48px of the short
 * one, and the conversation gets the entire height of the window.
 *
 * It is on the right rather than the left because the left edge belongs to the
 * conversation list. A reader's eye starts at the left and travels into the
 * answer; navigation between sections is the least frequent thing anybody does
 * here and belongs at the end of that journey, not the start.
 *
 * The active mark is a bar on the edge, not a filled tile. A filled tile at
 * this size is a button that looks pressed; a bar is a position indicator, and
 * position is what a rail communicates.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ComponentType } from "react";
import {
  ChatCircleIcon,
  ListChecksIcon,
  MagnifyingGlassIcon,
  SlidersHorizontalIcon,
  TreeStructureIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { HealthResponse } from "@/lib/contracts";
import { api, USE_MOCKS } from "@/lib/api";
import { dateTime } from "@/lib/format";
import { cx } from "@/components/ui/tone";

type IconType = ComponentType<{ size?: number; weight?: "bold" | "fill"; className?: string }>;

const NAV: ReadonlyArray<{ href: string; label: string; icon: IconType }> = [
  { href: "/ask", label: "Ask", icon: ChatCircleIcon },
  { href: "/brief", label: "Brief", icon: ListChecksIcon },
  { href: "/ops", label: "Rules", icon: SlidersHorizontalIcon },
  { href: "/architecture", label: "How", icon: TreeStructureIcon },
];

function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

export function SectionRail({ onOpenPalette }: { onOpenPalette?: () => void }) {
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
    <nav
      aria-label="Sections"
      className="flex w-14 shrink-0 flex-col items-center gap-1 bg-surface py-3 shadow-panel"
    >
      <Mark />

      <div className="h-3" />

      {NAV.map((item) => {
        const active = isActive(item.href, pathname);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cx(
              "relative flex w-full flex-col items-center gap-1 py-2 text-2xs font-medium",
              "transition-colors duration-200 ease-out-quint",
              // The active section is in the accent, not in plain ink. The
              // bar on the edge stays: it is what says WHERE, and the colour
              // is what makes it findable without reading four labels. Still
              // no filled tile, for the reason in the docstring.
              active ? "text-accent" : "text-ink-3 hover:text-ink-2",
            )}
          >
            {active ? (
              <span
                aria-hidden
                className="anim-fade-up absolute inset-y-1.5 right-0 w-[2px] rounded-full bg-[image:var(--grad-accent)]"
              />
            ) : null}
            <Icon size={17} weight={active ? "fill" : "bold"} />
            {item.label}
          </Link>
        );
      })}

      {onOpenPalette ? (
        <button
          type="button"
          onClick={onOpenPalette}
          title="Search. Ctrl K, or Cmd K on a Mac."
          aria-label="Search"
          className="mt-2 flex w-full flex-col items-center gap-1 py-2 text-2xs font-medium text-ink-3 hover:text-ink-2"
        >
          <MagnifyingGlassIcon size={17} weight="bold" />
          Find
        </button>
      ) : null}

      {/* The engine and the snapshot are the two things a controller has to
          know before they trust anything on screen, so they are on the rail
          rather than behind a menu. Hiding the mode would overstate the
          system. */}
      <div
        className="mt-auto flex flex-col items-center gap-2 pb-1"
        title={
          health
            ? `${health.llm_configured ? "An API key is configured, so the LangGraph agent plans each turn." : "No API key configured. The deterministic resolver answers, using the same tools and the same guard."}\nSnapshot ${dateTime(health.snapshot)}Z`
            : "Connecting to the API"
        }
      >
        {USE_MOCKS ? (
          <span className="size-1.5 rounded-full bg-caution" aria-label="Mock data" />
        ) : null}
        <span
          aria-hidden
          className={cx(
            "size-2 rounded-full",
            health ? (health.llm_configured ? "bg-accent" : "bg-pass") : "bg-line-strong",
          )}
        />
      </div>
    </nav>
  );
}

/**
 * The mark: a duty clock at the limit. Two strokes, no wordmark inside, so it
 * reads at 16px in a browser tab as easily as on the rail.
 */
function Mark() {
  return (
    <Link href="/" aria-label="Crew Ops Advisor, home" className="p-2">
      <svg width="20" height="20" viewBox="0 0 18 18" fill="none" aria-hidden>
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
    </Link>
  );
}
