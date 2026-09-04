import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * The shadcn class merger.
 *
 * `clsx` flattens conditionals, `tailwind-merge` resolves conflicts by
 * precedence rather than by source order, so a component's default `px-4` can
 * be overridden with `px-2` from a call site without the two both landing in
 * the class list and the cascade picking a winner at random.
 *
 * `cx` in `components/ui/tone.ts` stays. It is a plain join for the places
 * that only ever concatenate, and it costs nothing to call.
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
