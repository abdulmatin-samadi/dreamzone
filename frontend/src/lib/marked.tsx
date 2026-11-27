import type { ReactNode } from "react";

/** Text marked as **words** while importing the test is shown highlighted in yellow
 * (e.g. the words to use: "Complete with **in, at, or on**"). */
export function Marked({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return <>{parts.map((p, i): ReactNode => (i % 2 ? <mark key={i} className="rounded bg-yellow-300 px-1 text-slate-900">{p}</mark> : p))}</>;
}

/** The same text without the markers (for places that show plain text). */
export const unmark = (text: string) => text.replace(/\*\*(.+?)\*\*/g, "$1");
