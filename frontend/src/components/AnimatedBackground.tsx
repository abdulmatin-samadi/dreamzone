import type { CSSProperties } from "react";

/** Falling snow behind the content (styles in index.css: "snow"). */
// fixed pseudo-random layout (same on every render): every 3rd one is a ❄, the rest are soft dots
const rnd = (i: number, k: number) => { const v = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453; return v - Math.floor(v); };
const SNOW = Array.from({ length: 42 }, (_, i) => {
  const flake = i % 3 === 0;
  return {
    flake,
    style: {
      "--x": `${(rnd(i, 1) * 100).toFixed(2)}%`,
      "--s": flake ? `${10 + Math.round(rnd(i, 2) * 12)}px` : `${2 + Math.round(rnd(i, 2) * 4)}px`,
      "--d": `${14 + Math.round(rnd(i, 3) * 16)}s`,
      "--delay": `-${(rnd(i, 4) * 30).toFixed(1)}s`,
      "--sw": `${3 + Math.round(rnd(i, 5) * 4)}s`,
      opacity: 0.45 + rnd(i, 6) * 0.55,
    } as CSSProperties,
  };
});

export function AnimatedBackground() {
  return (
    <div className="dz-bg" aria-hidden>
      {SNOW.map((f, i) => <div key={i} className="dz-snow" style={f.style}>{f.flake ? <span>❄</span> : <span className="dot" />}</div>)}
    </div>
  );
}
