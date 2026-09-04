"use client";

/**
 * Shared state for the signature interaction.
 *
 * A figure in the prose, a cell in a table and a row in the evidence drawer
 * are three views of one `Fact`. Pointing at any of them lights the others.
 * That is the whole architecture made visible: the answer and its evidence are
 * the same object.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Fact } from "@/lib/contracts";

interface FactContextValue {
  facts: Map<string, Fact>;
  /** Transient, driven by hover and focus. */
  active: string | null;
  /** Sticky, driven by click. Survives the pointer leaving. */
  pinned: string | null;
  setActive: (key: string | null) => void;
  pin: (key: string | null) => void;
  /** True when the evidence drawer should be visible. */
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
}

const FactContext = createContext<FactContextValue | null>(null);

export function FactProvider({
  facts,
  children,
  drawerOpen,
  setDrawerOpen,
}: {
  facts: Fact[];
  children: ReactNode;
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
}) {
  const [active, setActive] = useState<string | null>(null);
  const [pinned, setPinned] = useState<string | null>(null);

  const index = useMemo(() => {
    const map = new Map<string, Fact>();
    for (const fact of facts) map.set(fact.key, fact);
    return map;
  }, [facts]);

  const pin = useCallback(
    (key: string | null) => {
      setPinned((current) => (current === key ? null : key));
      if (key) setDrawerOpen(true);
    },
    [setDrawerOpen],
  );

  /**
   * Clicking away puts a pinned popover down.
   *
   * Pinning survives the pointer leaving, which is the point of it: you can
   * click a figure, move to the evidence panel, and the link stays lit. What
   * was missing is any way to stop. Clicking the same chip toggled it off,
   * and clicking anywhere else did nothing at all, so a popover opened over
   * the paragraph somebody was reading and stayed there.
   *
   * Everything that is part of this interaction carries `data-fact-ui`, so a
   * press inside a chip or inside the popover is left alone and a press
   * anywhere else clears the pin.
   */
  useEffect(() => {
    if (pinned === null) return;

    const onPointer = (event: PointerEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.closest("[data-fact-ui]")) return;
      setPinned(null);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPinned(null);
    };

    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [pinned]);

  const value = useMemo(
    () => ({
      facts: index,
      active,
      pinned,
      setActive,
      pin,
      drawerOpen,
      setDrawerOpen,
    }),
    [index, active, pinned, pin, drawerOpen, setDrawerOpen],
  );

  return <FactContext.Provider value={value}>{children}</FactContext.Provider>;
}

export function useFacts(): FactContextValue {
  const context = useContext(FactContext);
  if (!context) {
    throw new Error("useFacts must be used inside a FactProvider");
  }
  return context;
}

/** Safe variant for components that may render outside a provider. */
export function useOptionalFacts(): FactContextValue | null {
  return useContext(FactContext);
}
