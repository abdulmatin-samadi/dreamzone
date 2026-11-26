import { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { ThemeToggle } from "./ThemeToggle";

const Feature = ({ icon, title, text }: { icon: ReactNode; title: string; text: string }) => (
  <li className="flex items-start gap-4">
    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15 text-white ring-1 ring-white/25 backdrop-blur">{icon}</span>
    <span><span className="block font-semibold text-white">{title}</span><span className="text-sm text-sky-100/80">{text}</span></span>
  </li>
);

const svg = (d: string) => (
  <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);

/** UZ / EN switch for the public pages. The choice is applied after sign-in for admins and teachers. */
function LanguageSwitch() {
  const { i18n } = useTranslation();
  const set = (code: string) => {
    void i18n.changeLanguage(code);
    localStorage.setItem("dz_lang", code);
    try { sessionStorage.setItem("dz_lang_pick", code); } catch { /* private mode */ }
  };
  return (
    <div className="flex overflow-hidden rounded-xl bg-white/15 p-1 ring-1 ring-white/30 backdrop-blur" role="group" aria-label="Language">
      {(["uz", "en"] as const).map((c) => (
        <button key={c} type="button" onClick={() => set(c)} aria-pressed={i18n.language === c}
          className={`rounded-lg px-3 py-1.5 text-sm font-semibold uppercase transition ${i18n.language === c ? "bg-white text-blue-700 shadow" : "text-white/85 hover:bg-white/15"}`}>{c}</button>
      ))}
    </div>
  );
}

/** Shared two-column layout for the public pages (login / register). */
export function AuthShell({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="relative flex min-h-full overflow-hidden bg-gradient-to-br from-[#051a3d] via-[#0a2a5e] to-[#0872d1]">
      <div className="dz-keep absolute right-4 top-4 z-20 flex items-center gap-2 sm:right-6 sm:top-6">
        <ThemeToggle className="h-[42px] w-[42px] rounded-xl bg-white/15 text-white/90 ring-1 ring-white/30 backdrop-blur hover:bg-white/25" />
        <LanguageSwitch />
      </div>
      {/* decorative background */}
      <div className="dz-keep pointer-events-none absolute inset-0" aria-hidden>
        <div className="anim-float-slow absolute -left-24 -top-24 h-96 w-96 rounded-full bg-cyan-400/30 blur-3xl" />
        <div className="anim-float-alt absolute -bottom-32 left-1/3 h-[28rem] w-[28rem] rounded-full bg-blue-500/30 blur-3xl" />
        <div className="anim-float-slow absolute -right-24 top-1/4 h-80 w-80 rounded-full bg-sky-300/25 blur-3xl" />
        <div className="absolute inset-0 opacity-[0.07]" style={{ backgroundImage: "radial-gradient(#fff 1px, transparent 1px)", backgroundSize: "26px 26px" }} />
        <div className="absolute right-[8%] top-[12%] hidden h-24 w-24 rounded-full border border-white/20 lg:block" />
        <div className="absolute bottom-[14%] left-[42%] hidden h-14 w-14 rounded-full border border-white/20 lg:block" />
      </div>

      {/* brand side */}
      <section className="dz-keep relative hidden w-1/2 flex-col justify-between p-12 lg:flex xl:p-16">
        <div className="anim-rise flex items-center gap-3">
          <img src="/logo.jpg" alt="Dreamzone" className="h-12 w-12 rounded-full ring-2 ring-white/40" />
          <span className="text-xl font-bold tracking-tight text-white">Dreamzone</span>
        </div>
        <div>
          <h2 className="anim-rise text-4xl font-extrabold leading-tight text-white xl:text-5xl" style={{ animationDelay: "0.1s" }}>
            {t("auth.headline1")}<br />
            <span className="bg-gradient-to-r from-cyan-300 to-sky-200 bg-clip-text text-transparent">{t("auth.headline2")}</span>
          </h2>
          <p className="anim-rise mt-4 max-w-md text-lg text-sky-100/80" style={{ animationDelay: "0.2s" }}>{t("auth.lead")}</p>
          <ul className="anim-rise mt-10 space-y-6" style={{ animationDelay: "0.3s" }}>
            <Feature icon={svg("M9 12l2 2 4-4M21 12a9 9 0 11-18 0 9 9 0 0118 0z")} title={t("auth.f1t")} text={t("auth.f1d")} />
            <Feature icon={svg("M12 6v6l4 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z")} title={t("auth.f2t")} text={t("auth.f2d")} />
            <Feature icon={svg("M5 13l4 4L19 7")} title={t("auth.f3t")} text={t("auth.f3d")} />
          </ul>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-medium text-sky-100/90">
          {["Elementary", "Pre-Intermediate", "Intermediate", "Pre-IELTS"].map((l, i) => (
            <span key={l} className="flex items-center gap-2 rounded-full bg-white/10 px-3 py-1.5 ring-1 ring-white/20 backdrop-blur">
              <span className="flex h-5 w-5 items-center justify-center rounded-full bg-cyan-400/80 text-[10px] font-bold text-[#051a3d]">{i + 1}</span>{l}
            </span>
          ))}
        </div>
      </section>

      {/* form side */}
      <section className="relative flex w-full items-center justify-center p-4 sm:p-8 lg:w-1/2">
        <div className="anim-rise w-full max-w-md rounded-3xl border border-white/30 bg-white/90 p-7 shadow-2xl shadow-blue-950/40 backdrop-blur-xl sm:p-9">
          <div className="mb-6 flex items-center gap-3 lg:hidden">
            <img src="/logo.jpg" alt="Dreamzone" className="h-11 w-11 rounded-full shadow shadow-sky-300" />
            <span className="text-lg font-bold text-slate-900">Dreamzone</span>
          </div>
          {children}
        </div>
      </section>
    </div>
  );
}
