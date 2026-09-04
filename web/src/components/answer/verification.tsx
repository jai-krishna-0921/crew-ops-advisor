"use client";

/**
 * The guard's own record, shown rather than hidden.
 *
 * A system that checks itself and does not say so gets no credit for it. The
 * counts are always visible; the atoms it could not attest are one click away
 * and are the most useful thing on the card when something went wrong.
 */

import {
  SealCheckIcon,
  ShieldWarningIcon,
  SlidersIcon,
  XCircleIcon,
} from "@phosphor-icons/react/dist/ssr";

import type { VerificationReport, VerificationStatus } from "@/lib/contracts";
import {
  grouped,
  VERIFICATION_LABEL,
  VERIFICATION_TONE,
} from "@/lib/format";
import { Disclosure, Pill, Token } from "@/components/ui/primitives";

const ICON: Record<VerificationStatus, typeof SealCheckIcon> = {
  verified: SealCheckIcon,
  repaired: SlidersIcon,
  rejected: XCircleIcon,
  skipped: ShieldWarningIcon,
};

const EXPLAIN: Record<VerificationStatus, string> = {
  verified:
    "Every number, identifier, date and rule id in this answer matched a fact a tool produced during this turn.",
  repaired:
    "The first draft carried an atom no tool supported. The turn was sent back once and the corrected answer passed.",
  rejected:
    "The draft answer carried atoms no tool supported, and a repair pass did not fix them, so the answer was refused.",
  skipped:
    "There were no figures to check. A refusal states no numbers, so there is nothing to attest.",
};

export function VerificationBadge({ report }: { report: VerificationReport }) {
  const Icon = ICON[report.status];
  return (
    <Pill tone={VERIFICATION_TONE[report.status]} title={EXPLAIN[report.status]}>
      <Icon size={11} weight="fill" aria-hidden />
      {VERIFICATION_LABEL[report.status]}
      {report.checked_atoms > 0 ? (
        <span className="num ml-0.5 font-normal opacity-80">
          {grouped(report.attested_atoms)}/{grouped(report.checked_atoms)}
        </span>
      ) : null}
    </Pill>
  );
}

export function VerificationPanel({ report }: { report: VerificationReport }) {
  return (
    <section
      aria-label="Grounding check"
      className="rounded-md bg-surface hairline"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <h3 className="text-base font-semibold text-ink">Grounding check</h3>
        <VerificationBadge report={report} />
        {report.repair_attempts > 0 ? (
          <span className="text-xs text-ink-3">
            {grouped(report.repair_attempts)} repair pass
            {report.repair_attempts === 1 ? "" : "es"}
          </span>
        ) : null}
      </header>

      <p className="max-w-[68ch] px-3 py-2 text-base leading-relaxed text-ink-2">
        {EXPLAIN[report.status]}
      </p>

      {report.note ? (
        <p className="border-t border-line-soft px-3 py-2 text-base text-ink-2">
          {report.note}
        </p>
      ) : null}

      {report.unattested.length > 0 ? (
        <div className="border-t border-line-soft px-2 py-1.5">
          <Disclosure
            summary="Atoms the guard could not attest"
            count={report.unattested.length}
            tone="breach"
            defaultOpen
          >
            <ul className="space-y-1.5 px-1 pb-2">
              {report.unattested.map((atom, index) => (
                <li
                  key={index}
                  className="rounded-sm bg-breach-wash px-2 py-1.5 ring-1 ring-breach-line"
                >
                  <div className="flex items-center gap-2">
                    <Token className="text-breach">{atom.atom}</Token>
                    <span className="label-micro">{atom.kind}</span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-2 italic">
                    &ldquo;{atom.context}&rdquo;
                  </p>
                </li>
              ))}
            </ul>
          </Disclosure>
        </div>
      ) : null}
    </section>
  );
}
