"use client";

/**
 * A draggable splitter, and the width it controls.
 *
 * WHY THIS IS ~70 LINES RATHER THAN `react-resizable-panels`. That library is
 * the right answer for a layout of panels that share a viewport and should
 * divide it proportionally, which is what an editor's document area is. A
 * sidebar is not that. It holds a list of names at a legible width, and it
 * should still be that width when the window changes size: a percentage rail
 * is 260px on a laptop and 420px on a monitor, which is 420px of whitespace
 * beside a truncated title. So the width here is pixels, clamped, and stored.
 *
 * The interaction is pointer events with capture, which is what makes a drag
 * survive the cursor leaving the 5px handle. `setPointerCapture` routes every
 * subsequent move to the element that captured it until release, so there is
 * no document-level listener to install, leak, or fight with an iframe.
 *
 * THE HANDLE IS A REAL SEPARATOR. `role="separator"` with `aria-valuenow`, and
 * arrow keys move it, because a resize that can only be performed with a mouse
 * is a resize half the people at a desk cannot perform at all. Double click
 * returns it to the default, which is the escape hatch for having dragged it
 * somewhere useless.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export interface ResizeBounds {
  min: number;
  max: number;
  initial: number;
}

/**
 * A stored, clamped pixel width.
 *
 * Read back after mount rather than in a lazy initialiser: the server has no
 * localStorage, and disagreeing with the server render blows up hydration.
 */
export function useResizableWidth(
  key: string,
  { min, max, initial }: ResizeBounds,
) {
  const [width, setWidth] = useState(initial);

  useEffect(() => {
    try {
      const stored = Number(window.localStorage.getItem(key));
      if (Number.isFinite(stored) && stored > 0) {
        // eslint-disable-next-line react-hooks/set-state-in-effect -- post-mount rehydration
        setWidth(Math.min(max, Math.max(min, stored)));
      }
    } catch {
      // Private mode or blocked site data. The default stands.
    }
  }, [key, min, max]);

  const commit = useCallback(
    (next: number) => {
      const clamped = Math.min(max, Math.max(min, Math.round(next)));
      setWidth(clamped);
      try {
        window.localStorage.setItem(key, String(clamped));
      } catch {
        // Losing the preference is smaller than throwing here.
      }
    },
    [key, min, max],
  );

  const reset = useCallback(() => commit(initial), [commit, initial]);

  return { width, commit, reset, min, max };
}

/**
 * The splitter itself.
 *
 * `side` says which edge of the panel it sits on, which is the only thing that
 * differs between a rail on the left and a drawer on the right: dragging right
 * widens the first and narrows the second.
 */
export function ResizeHandle({
  width,
  min,
  max,
  onResize,
  onReset,
  onDragChange,
  side = "right",
  label,
  className,
}: {
  width: number;
  min: number;
  max: number;
  onResize: (next: number) => void;
  onReset?: () => void;
  /** So the panel can drop its width transition while a drag is running. */
  onDragChange?: (dragging: boolean) => void;
  side?: "left" | "right";
  label: string;
  className?: string;
}) {
  const origin = useRef<{ x: number; width: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  useDragCursor(dragging);
  useEffect(() => {
    onDragChange?.(dragging);
  }, [dragging, onDragChange]);

  const direction = side === "right" ? 1 : -1;

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      onPointerDown={(event) => {
        // Left button only. A right click here belongs to the context menu.
        if (event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        origin.current = { x: event.clientX, width };
        setDragging(true);
      }}
      onPointerMove={(event) => {
        const start = origin.current;
        if (!start) return;
        onResize(start.width + (event.clientX - start.x) * direction);
      }}
      onPointerUp={(event) => {
        event.currentTarget.releasePointerCapture(event.pointerId);
        origin.current = null;
        setDragging(false);
      }}
      onDoubleClick={onReset}
      onKeyDown={(event) => {
        const step = event.shiftKey ? 48 : 16;
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          onResize(width - step * direction);
        }
        if (event.key === "ArrowRight") {
          event.preventDefault();
          onResize(width + step * direction);
        }
        if (event.key === "Home" && onReset) {
          event.preventDefault();
          onReset();
        }
      }}
      className={cn(
        // Wider than it looks. The visible line is 1px and the grab area is
        // 9px, because a 1px target is a target people miss.
        "group/handle relative w-[9px] shrink-0 cursor-col-resize touch-none select-none",
        "before:absolute before:inset-y-0 before:left-1/2 before:w-px before:-translate-x-1/2",
        "before:bg-line-soft before:transition-colors before:duration-150",
        "hover:before:bg-accent-line focus-visible:before:bg-accent",
        dragging && "before:bg-accent",
        className,
      )}
    >
      {/* A grip, shown only on approach, so the edge is quiet until somebody
          goes looking for it. */}
      <span
        aria-hidden
        className={cn(
          "absolute top-1/2 left-1/2 h-8 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full",
          "bg-line-strong opacity-0 transition-opacity duration-150",
          "group-hover/handle:opacity-100",
          dragging && "bg-accent opacity-100",
        )}
      />
    </div>
  );
}

/**
 * While a drag is running, the whole document gets the resize cursor and stops
 * selecting text. Without it the cursor flickers back to a caret the moment
 * the pointer crosses a paragraph, and the drag looks broken while working
 * perfectly.
 */
function useDragCursor(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const previous = document.body.style.cursor;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.cursor = previous;
      document.body.style.userSelect = "";
    };
  }, [active]);
}
