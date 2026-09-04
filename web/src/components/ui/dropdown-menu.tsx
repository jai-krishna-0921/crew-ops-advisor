"use client";

/**
 * A dropdown menu, on Radix.
 *
 * REPLACES A HAND-ROLLED MENU THAT COST THREE BUGS TO GET WRONG. It was an
 * absolutely positioned div plus a full-viewport invisible button for
 * dismissal, and between them they produced: a menu trapped inside the
 * stacking context its own entry animation created, so the rows below painted
 * over it; a backdrop that swallowed every click meant for the item behind it,
 * so the menu opened and did nothing; and a field that focused inside the
 * click that opened it and lost the caret again on the way out.
 *
 * Radix portals the content to the body, which is what makes the stacking
 * problem impossible rather than fixed, and it owns dismissal, focus return
 * and typeahead. None of that is interesting work and all of it is easy to get
 * subtly wrong.
 */

import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const DropdownMenu = DropdownMenuPrimitive.Root;
export const DropdownMenuTrigger = DropdownMenuPrimitive.Trigger;

export function DropdownMenuContent({
  className,
  sideOffset = 4,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Content>) {
  return (
    <DropdownMenuPrimitive.Portal>
      <DropdownMenuPrimitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 min-w-36 overflow-hidden rounded-sm bg-surface py-1 shadow-pop",
          "anim-fade-up",
          className,
        )}
        {...props}
      />
    </DropdownMenuPrimitive.Portal>
  );
}

export function DropdownMenuItem({
  className,
  tone,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Item> & { tone?: "breach" }) {
  return (
    <DropdownMenuPrimitive.Item
      className={cn(
        "flex cursor-pointer items-center gap-2 px-2.5 py-1.5 text-base outline-none select-none",
        tone === "breach"
          ? "text-breach focus:bg-breach-wash"
          : "text-ink-2 focus:bg-hover focus:text-ink",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuSeparator({
  className,
  ...props
}: ComponentProps<typeof DropdownMenuPrimitive.Separator>) {
  return (
    <DropdownMenuPrimitive.Separator
      className={cn("my-1 h-px bg-line-soft", className)}
      {...props}
    />
  );
}
