import { useSyncExternalStore } from "react";

/** Light / dark theme. The class on <html> drives the palette (see index.css, "dark theme");
 * index.html applies the saved choice before the first paint, so there is no flash. */
export type Theme = "light" | "dark";

const KEY = "dz_theme";
const listeners = new Set<() => void>();
const root = () => document.documentElement;
const current = (): Theme => (root().classList.contains("dark") ? "dark" : "light");
const notify = () => listeners.forEach((l) => l());

export function setTheme(theme: Theme) {
  root().classList.toggle("dark", theme === "dark");
  try { localStorage.setItem(KEY, theme); } catch { /* storage blocked: the choice lasts until the page is closed */ }
  notify();
}

// the theme was changed in another tab
window.addEventListener("storage", (e) => {
  if (e.key === KEY && (e.newValue === "dark" || e.newValue === "light")) {
    root().classList.toggle("dark", e.newValue === "dark");
    notify();
  }
});

export function useTheme() {
  const theme = useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; },
    current,
    (): Theme => "light",
  );
  return { theme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}
