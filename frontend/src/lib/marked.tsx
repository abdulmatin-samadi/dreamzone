import type { ReactNode } from "react";

/** Fixed colours (not theme classes): in the dark theme the yellow stays yellow and the words stay black.
 * Text marked as **words** while importing the test is shown highlighted in yellow
 * (e.g. the words to use: "Complete with **in, at, or on**"). */
export function Marked({ text }: { text: string }) {
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return <>{parts.map((p, i): ReactNode => (i % 2 ? <mark key={i} className="rounded px-1" style={{ background: "#fde047", color: "#111827" }}>{p}</mark> : p))}</>;
}

/** The same text without the markers (for places that show plain text). */
export const unmark = (text: string) => text.replace(/\*\*(.+?)\*\*/g, "$1");

const WORD = "[A-Za-z'’-]+";
const RULES: RegExp[] = [
  // the words of a box: "Complete the text  [live come speak]"
  /\[([^\]!?.'"\u2018\u2019\u201c\u201d]+)\]/g,
  // quoted words: “so” or “because”, "like" or "would like"
  /([“"][^”"]+[”"](?:\s+or\s+[“"][^”"]+[”"])?)/g,
  // after a dash: "preposition - in, at, or on."
  new RegExp(`\\s-\\s(${WORD}(?:,?\\s+(?:or\\s+)?${WORD}){1,12})(?=\\s*[.:]?\\s*$)`, "g"),
  // a list after a colon: "Choose the correct word: WHO, WHICH or WHERE." / "a prefix: dis-, il-, im-"
  new RegExp(`:\\s+(${WORD}(?:,\\s*${WORD})+(?:,?\\s+or\\s+${WORD})?|${WORD},?\\s+or\\s+${WORD})(?=\\s*\\.?\\s*$)`, "g"),
  // a list after "with": "with me, you, him, her, it, us, them" / "with am, is or are"
  new RegExp(`\\bwith\\s+(${WORD}(?:,\\s*${WORD}){2,}(?:,?\\s+or\\s+${WORD})?|${WORD}(?:,\\s*${WORD})*,?\\s+or\\s+${WORD})(?=\\s*(?:\\.|$))`, "g"),
  // "There is or There are", "TRUE or FALSE"
  /\b([Tt]here\s+(?:is|are)\s+or\s+[Tt]here\s+(?:is|are)|TRUE or FALSE|True or False)\b/g,
  // slash choices: "There is / There are", "is/are/have/ has", "is/are or have/has"
  /\b((?:[Tt]here\s+)?[A-Za-z']+(?:\s*\/\s*(?:[Tt]here\s+)?[A-Za-z']+)+(?:\s+or\s+[A-Za-z']+(?:\s*\/\s*[A-Za-z']+)+)?)/g,
];

/** Exercise headings saved before the highlight existed: find the words to use and mark them. */
export function autoMark(text: string): string {
  if (!text || text.includes("**")) return text;
  let out = text;
  for (const re of RULES) {
    out = out.replace(re, (whole: string, words: string) => {
      if (!words || out.includes(`**${words}**`)) return whole;
      return whole.replace(words, `**${words}**`);
    });
    if (out.includes("**")) break;  // one highlight per heading is enough
  }
  return out;
}
