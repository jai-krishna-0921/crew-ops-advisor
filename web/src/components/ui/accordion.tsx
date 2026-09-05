"use client";

/**
 * The accordion, on Radix.
 *
 * The seven rules are the specification this product is held to, and a landing
 * page that prints all seven constraints in full is a wall nobody reads. Each
 * one opens to its constraint and to the arithmetic behind it, which is the
 * thing worth showing: the rules are not a feature list, they are the reason
 * a model is not allowed to compute the answer.
 *
 * Radix rather than `<details>` because the height animates. A `<details>`
 * snaps, and a snap on a page whose whole argument is care reads as a page
 * built in a hurry. Radix publishes the panel's measured height as
 * `--radix-accordion-content-height`, which is what makes a real transition
 * possible without measuring anything by hand.
 *
 * The toggle is a plus that rotates into a minus. Two strokes, one of which
 * turns 90 degrees, so the mark is continuous through the change rather than
 * one glyph being swapped for another.
 */

import * as AccordionPrimitive from "@radix-ui/react-accordion";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const Accordion = AccordionPrimitive.Root;

export function AccordionItem({
  className,
  ...props
}: ComponentProps<typeof AccordionPrimitive.Item>) {
  return (
    <AccordionPrimitive.Item
      className={cn(
        "group/item relative overflow-hidden rounded-2xl transition-colors duration-500 ease-out-quint",
        "data-[state=open]:bg-surface data-[state=open]:shadow-panel",
        className,
      )}
      {...props}
    />
  );
}

export function AccordionTrigger({
  className,
  children,
  ...props
}: ComponentProps<typeof AccordionPrimitive.Trigger>) {
  return (
    <AccordionPrimitive.Header className="flex">
      <AccordionPrimitive.Trigger
        className={cn(
          "group/trigger flex flex-1 cursor-pointer items-center gap-4 px-5 py-5 text-left",
          "transition-colors duration-300 ease-out-quint hover:text-ink",
          className,
        )}
        {...props}
      >
        <span className="min-w-0 flex-1">{children}</span>
        <span
          aria-hidden
          className="relative grid size-8 shrink-0 place-items-center rounded-full bg-inset transition-colors duration-300 ease-out-quint group-hover/trigger:bg-hover"
        >
          <span className="absolute h-px w-3 rounded-full bg-ink-2" />
          <span className="absolute h-px w-3 rounded-full bg-ink-2 rotate-90 transition-transform duration-500 ease-out-quint group-data-[state=open]/item:rotate-0" />
        </span>
      </AccordionPrimitive.Trigger>
    </AccordionPrimitive.Header>
  );
}

export function AccordionContent({
  className,
  children,
  ...props
}: ComponentProps<typeof AccordionPrimitive.Content>) {
  return (
    <AccordionPrimitive.Content
      className="overflow-hidden data-[state=closed]:anim-accordion-up data-[state=open]:anim-accordion-down"
      {...props}
    >
      <div className={cn("px-5 pt-0 pb-5", className)}>{children}</div>
    </AccordionPrimitive.Content>
  );
}
