"use client";

/**
 * The button, on the shadcn pattern: one component, variants in `cva`.
 *
 * It exists for the landing page. The console does not need it: the composer's
 * send control, the rail's new conversation and the ops panels' run buttons
 * are each one button on one surface with one job, and a variant table for
 * three of those is indirection without a payoff. A marketing page has the
 * same shape of button in eight places at three sizes, which is when a table
 * starts paying.
 *
 * THE TRAILING ICON SITS IN ITS OWN CIRCLE. An arrow set naked beside a label
 * reads as punctuation; the same arrow inside a disc reads as a place the
 * press is going. It also gives the hover something to do that is not a colour
 * change: the disc moves and grows a little inside a button that is itself
 * pressing down, and those two motions in opposite directions are what make a
 * flat rectangle feel like a physical control.
 */

import Link from "next/link";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

const button = cva(
  [
    "group relative inline-flex cursor-pointer items-center justify-center gap-2",
    "font-semibold whitespace-nowrap select-none",
    // A spring rather than a fade. `ease-out-quint` is the project's own
    // curve and it decelerates hard, which is what reads as mass.
    "transition-[transform,box-shadow,background-color,color] duration-300 ease-out-quint",
    "active:scale-[0.985] focus-visible:outline-2 focus-visible:outline-offset-2",
    "focus-visible:outline-accent disabled:pointer-events-none disabled:opacity-50",
  ],
  {
    variants: {
      variant: {
        primary:
          "bg-[image:var(--grad-accent)] text-page shadow-panel hover:-translate-y-0.5 hover:shadow-pop",
        secondary:
          "bg-surface text-ink hairline hover:-translate-y-0.5 hover:shadow-panel",
        ghost: "text-ink-2 hover:bg-hover hover:text-ink",
        outline:
          "bg-transparent text-ink shadow-[inset_0_0_0_1px_var(--line-strong)] hover:bg-surface hover:shadow-[inset_0_0_0_1px_var(--line-strong),var(--shadow-panel)]",
      },
      size: {
        sm: "h-9 rounded-full px-4 text-base",
        md: "h-11 rounded-full px-5 text-md",
        lg: "h-14 rounded-full px-6 text-md",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

/** The disc the trailing icon lives in, sized against the button. */
const disc = cva(
  [
    "flex shrink-0 items-center justify-center rounded-full",
    "transition-transform duration-300 ease-out-quint",
    "group-hover:translate-x-0.5 group-hover:-translate-y-px group-hover:scale-105",
  ],
  {
    variants: {
      variant: {
        primary: "bg-page/20 text-page",
        secondary: "bg-inset text-ink-2",
        ghost: "bg-inset text-ink-2",
        outline: "bg-inset text-ink-2",
      },
      size: { sm: "size-6", md: "size-7", lg: "size-9" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

type Style = VariantProps<typeof button>;

interface Shared extends Style {
  children: ReactNode;
  /** Rendered inside its own disc, flush with the right inner padding. */
  trailing?: ReactNode;
  className?: string;
}

function Inner({ children, trailing, variant, size }: Shared) {
  return (
    <>
      <span className={trailing ? "pl-1" : undefined}>{children}</span>
      {trailing ? (
        <span aria-hidden className={cn(disc({ variant, size }), "-mr-2")}>
          {trailing}
        </span>
      ) : null}
    </>
  );
}

export function Button({
  children,
  trailing,
  variant,
  size,
  className,
  ...rest
}: Shared & Omit<ComponentProps<"button">, "children" | "className">) {
  return (
    <button className={cn(button({ variant, size }), className)} {...rest}>
      <Inner variant={variant} size={size} trailing={trailing}>
        {children}
      </Inner>
    </button>
  );
}

export function ButtonLink({
  children,
  trailing,
  variant,
  size,
  className,
  ...rest
}: Shared & Omit<ComponentProps<typeof Link>, "children" | "className">) {
  return (
    <Link className={cn(button({ variant, size }), className)} {...rest}>
      <Inner variant={variant} size={size} trailing={trailing}>
        {children}
      </Inner>
    </Link>
  );
}
