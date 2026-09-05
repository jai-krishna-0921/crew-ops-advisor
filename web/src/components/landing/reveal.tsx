"use client";

/**
 * Scroll entry, on `IntersectionObserver`.
 *
 * No scroll listener. A `scroll` handler fires on every frame of every wheel
 * tick and each call reads layout to decide whether an element is visible,
 * which is a forced reflow per frame per element: on a page with thirty
 * revealing blocks that is what turns a phone's scroll to mush. The observer
 * is told once what to watch and reports only when the answer changes.
 *
 * `once` by default, and the observer unsubscribes the moment an element has
 * arrived. An element that fades back out when it leaves the viewport is a
 * page that will not sit still while it is being read.
 *
 * The transform is the whole animation: translate, blur and opacity, no
 * layout property anywhere near it, so the compositor does all of it. The
 * blur is what separates this from a fade. Sixteen pixels of travel with a
 * fade is a web page; the same travel resolving out of a blur reads as
 * something coming into focus, which is a physical event rather than a CSS
 * one.
 *
 * REDUCED MOTION IS HANDLED IN THE STYLESHEET, NOT HERE. This component read
 * the media query itself and set state to skip the animation, which is the
 * same rule written twice: `globals.css` already collapses every transition in
 * the application to nothing when the query matches. With the duplicate gone,
 * a reader who has asked for less motion gets exactly the same behaviour,
 * blocks appearing as they are reached, with no travel and no blur, and this
 * file goes back to having one job.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Always a `div`, deliberately. A polymorphic `as` would let this stand in for
 * the section or list item it wraps, which sounds tidier and buys a generic
 * ref type and nothing else: this element carries no meaning, only a
 * transform, so the semantic element belongs outside it or inside it.
 */
export function Reveal({
  children,
  className,
  /** Milliseconds behind the block above, for a staggered row. */
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        setShown(true);
        observer.disconnect();
      },
      // A little inside the fold rather than exactly on it, so a block has
      // finished arriving by the time it is somewhere a reader is looking.
      //
      // THRESHOLD ZERO, AND ONLY 8 PERCENT OF INSET. Both numbers are about
      // the last element on the page. Shrinking the observation box from the
      // bottom means an element can only reveal once it is that far up the
      // window, and the footer never can be: at maximum scroll it sits in the
      // bottom tenth and there is nowhere further to go. Asking for 5 percent
      // of it to be inside the shrunk box made that certain. With a zero
      // threshold a single overlapping pixel is enough, so anything a reader
      // can reach will arrive.
      { rootMargin: "0px 0px -8% 0px", threshold: 0 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{ transitionDelay: `${delay}ms` }}
      className={cn(
        "transition-[opacity,transform,filter] duration-[900ms] ease-out-quint will-change-[transform,opacity]",
        shown
          ? "translate-y-0 opacity-100 blur-none"
          : "translate-y-10 opacity-0 blur-[6px]",
        className,
      )}
    >
      {children}
    </div>
  );
}
