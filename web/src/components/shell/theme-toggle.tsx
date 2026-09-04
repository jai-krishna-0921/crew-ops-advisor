"use client";

/**
 * Light, system, dark.
 *
 * The stored choice is an external store, so it is read through
 * `useSyncExternalStore` rather than copied into state inside an effect. That
 * keeps the server render and the hydration render agreeing on "system" and
 * lets the real value arrive without a cascading re-render.
 */

import { useCallback, useSyncExternalStore } from "react";
import { DesktopIcon, MoonIcon, SunIcon } from "@phosphor-icons/react/dist/ssr";

import { cx } from "@/components/ui/tone";

type Theme = "system" | "light" | "dark";

const STORAGE_KEY = "crewops.theme";
const CHANGE_EVENT = "crewops:theme";

const OPTIONS: { value: Theme; label: string; Icon: typeof SunIcon }[] = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "system", label: "System", Icon: DesktopIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
];

function subscribe(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(CHANGE_EVENT, onChange);
  };
}

function readTheme(): Theme {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "light" || stored === "dark" ? stored : "system";
  } catch {
    // Storage can be unavailable. System is a correct answer, not a fallback.
    return "system";
  }
}

const serverTheme = (): Theme => "system";

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, readTheme, serverTheme);

  const apply = useCallback((next: Theme) => {
    const root = document.documentElement;
    if (next === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", next);
    try {
      if (next === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // The choice still applies for this session even if it cannot persist.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return (
    <div
      role="group"
      aria-label="Colour theme"
      className="inline-flex items-center gap-0.5 rounded-sm bg-inset p-0.5 ring-1 ring-line"
    >
      {OPTIONS.map(({ value, label, Icon }) => (
        <button
          key={value}
          type="button"
          aria-label={label}
          title={label}
          aria-pressed={theme === value}
          onClick={() => apply(value)}
          className={cx(
            "inline-flex h-5 w-5 items-center justify-center rounded-xs transition-colors duration-100",
            theme === value
              ? "bg-surface text-ink hairline"
              : "text-ink-3 hover:text-ink-2",
          )}
        >
          <Icon size={11} weight="bold" aria-hidden />
        </button>
      ))}
    </div>
  );
}
