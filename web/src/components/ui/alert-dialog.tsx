"use client";

/**
 * A confirmation dialog, on Radix.
 *
 * REPLACES A HAND-ROLLED CONFIRM THAT WAS QUIETLY BROKEN. Deleting a
 * conversation asked in the row itself, which sounds tidy and was not: the row
 * was inside a scrolling list, the confirm competed with the row's own click
 * target, and nothing about it trapped focus or announced itself. Radix gives
 * the modal semantics for free (focus trap, escape, `role="alertdialog"`, the
 * initial focus on the safe action), and those are exactly the parts nobody
 * hand-rolls correctly.
 *
 * `alert-dialog` rather than `dialog`, deliberately. An alert dialog has no
 * dismiss-by-backdrop and no close button: it is for a question that has to be
 * answered rather than a panel that can be waved away, and deleting an audit
 * trail is that kind of question.
 */

import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export const AlertDialog = AlertDialogPrimitive.Root;
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger;
export const AlertDialogPortal = AlertDialogPrimitive.Portal;

export function AlertDialogOverlay({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Overlay>) {
  return (
    <AlertDialogPrimitive.Overlay
      className={cn(
        // No `tailwindcss-animate`. The entry animations here are the two
        // this product already defines, so the dialog moves on the same
        // curves as everything else rather than importing a second system.
        "fixed inset-0 z-50 bg-ink/25 backdrop-blur-[2px] anim-fade-up",
        className,
      )}
      {...props}
    />
  );
}

export function AlertDialogContent({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Content>) {
  return (
    <AlertDialogPortal>
      <AlertDialogOverlay />
      <AlertDialogPrimitive.Content
        className={cn(
          "fixed top-1/2 left-1/2 z-50 w-[min(28rem,calc(100vw-2rem))]",
          "-translate-x-1/2 -translate-y-1/2",
          "rounded-lg bg-surface p-5 shadow-pop",
          "anim-slide-down",
          className,
        )}
        {...props}
      />
    </AlertDialogPortal>
  );
}

export function AlertDialogHeader({
  className,
  ...props
}: ComponentProps<"div">) {
  return <div className={cn("space-y-1.5", className)} {...props} />;
}

export function AlertDialogFooter({
  className,
  ...props
}: ComponentProps<"div">) {
  return (
    <div
      className={cn("mt-5 flex flex-row items-center justify-end gap-2", className)}
      {...props}
    />
  );
}

export function AlertDialogTitle({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Title>) {
  return (
    <AlertDialogPrimitive.Title
      className={cn("macro text-lg text-ink", className)}
      {...props}
    />
  );
}

export function AlertDialogDescription({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Description>) {
  return (
    <AlertDialogPrimitive.Description
      className={cn("text-base leading-relaxed text-ink-2", className)}
      {...props}
    />
  );
}

export function AlertDialogAction({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Action>) {
  return (
    <AlertDialogPrimitive.Action
      className={cn(
        "inline-flex cursor-pointer items-center justify-center rounded-sm px-3 py-1.5",
        "bg-breach text-page hover:opacity-90",
        "text-base font-medium",
        className,
      )}
      {...props}
    />
  );
}

export function AlertDialogCancel({
  className,
  ...props
}: ComponentProps<typeof AlertDialogPrimitive.Cancel>) {
  return (
    <AlertDialogPrimitive.Cancel
      className={cn(
        "inline-flex cursor-pointer items-center justify-center rounded-sm px-3 py-1.5",
        "bg-inset text-ink-2 hover:bg-hover hover:text-ink",
        "text-base font-medium",
        className,
      )}
      {...props}
    />
  );
}
