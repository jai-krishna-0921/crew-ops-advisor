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
