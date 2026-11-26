// Verifies every statically used translation key exists in all locales and that locales have identical keys.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const root = new URL("../src", import.meta.url).pathname;
const flatten = (o, p = "") => Object.entries(o).flatMap(([k, v]) => (typeof v === "object" ? flatten(v, `${p}${k}.`) : [`${p}${k}`]));

// transpile-free load of the locale files (they are plain object literals)
const load = (f) => {
  const src = readFileSync(join(root, "i18n/locales", f), "utf8")
    .replace(/^import .*$/gm, "").replace(/type Dict[\s\S]*?\n\n/, "").replace(/: Dict<typeof en>/, "").replace("export default en;", "return en;").replace("export default uz;", "return uz;");
  return new Function(src)();
};
const locales = { en: flatten(load("en.ts")), uz: flatten(load("uz.ts")) };
let bad = 0;
for (const [a, b] of [["en", "uz"], ["uz", "en"]]) for (const k of locales[a]) if (!locales[b].includes(k)) { console.error(`missing in ${b}: ${k}`); bad++; }

const files = [];
(function walk(d) { for (const f of readdirSync(d)) { const p = join(d, f); statSync(p).isDirectory() ? walk(p) : /\.tsx?$/.test(f) && files.push(p); } })(root);
const used = new Set();
for (const f of files) {
  const s = readFileSync(f, "utf8");
  for (const m of s.matchAll(/\b(?:t|notify\.ok)\(\s*"([\w.]+)"/g)) used.add(m[1]);
  for (const m of s.matchAll(/label: "(nav\.\w+)"|label: t\("(\w+\.\w+)"\)/g)) used.add(m[1] || m[2]);
  for (const m of s.matchAll(/(?:notify\.ok|t)\(\s*cond\?/g)) void m;
}
for (const k of used) if (!locales.en.includes(k)) { console.error(`used but undefined: ${k}`); bad++; }
console.log(`${used.size} static keys checked, ${locales.en.length} keys per locale.`);
process.exit(bad ? 1 : 0);
