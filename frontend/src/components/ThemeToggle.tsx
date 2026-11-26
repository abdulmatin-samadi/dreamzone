import { useTranslation } from "react-i18next";

import { useTheme } from "../lib/theme";
import { cx } from "./ui";

const SUN = "M12 3v2M12 19v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M3 12h2M19 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4M12 8a4 4 0 100 8 4 4 0 000-8z";
const MOON = "M20.5 14.5A8.5 8.5 0 019.5 3.5a8.5 8.5 0 1011 11z";

/** Light / dark switch: shows the moon in the light theme and the sun in the dark one. */
export function ThemeToggle({ className }: { className?: string }) {
  const { t } = useTranslation();
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  const label = dark ? t("theme.toLight") : t("theme.toDark");
  return (
    <button type="button" onClick={toggle} aria-label={label} title={label} aria-pressed={dark}
      className={cx("inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition", className)}>
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d={dark ? SUN : MOON} />
      </svg>
    </button>
  );
}
