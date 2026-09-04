"use client";

import { useEffect, useState } from "react";
import { DesktopIcon, MoonIcon, SunIcon } from "@phosphor-icons/react/dist/ssr";

import { cx } from "@/components/ui/tone";

type Theme = "system" | "light" | "dark";

const STORAGE_KEY = "crewops.theme";

const OPTIONS: { value: Theme; label: string; Icon: typeof SunIcon }[] = [
  { value: "light", label: "Light", Icon: SunIcon },
  { value: "system", label: "System", Icon: DesktopIcon },
  { value: "dark", label: "Dark", Icon: MoonIcon },
];

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "light" || stored === "dark") setTheme(stored);
    } catch {
      // Storage can be unavailable. The system default is a fine fallback.
    }
    setReady(true);
  }, []);

  const apply = (next: Theme) => {
    setTheme(next);
    const root = document.documentElement;
    if (next === "system") {
      root.removeAttribute("data-theme");
    } else {
      root.setAttribute("data-theme", next);
    }
    try {
      if (next === "system") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Ignore: the choice still applies for this session.
    }
  };

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
          aria-pressed={ready && theme === value}
          onClick={() => apply(value)}
          className={cx(
            "inline-flex h-5 w-5 items-center justify-center rounded-xs transition-colors duration-100",
            ready && theme === value
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
