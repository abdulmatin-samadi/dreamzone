import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api, parseError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { useNotify } from "../components/Toast";
import { Button, Input } from "../components/ui";

/** Self-registration: details + "I am not a robot" -> signed in straight away. */
export default function RegisterPage() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const notify = useNotify();
  const nav = useNavigate();
  const [f, setF] = useState({ first_name: "", last_name: "", username: "", password: "", confirm: "", website: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  // robot check
  const [human, setHuman] = useState(false);
  const [captcha, setCaptcha] = useState<{ token: string; image: string } | null>(null);
  const [answer, setAnswer] = useState("");
  const loadCaptcha = async () => {
    setAnswer("");
    try { const { data } = await api.get<{ token: string; image: string }>("/auth/captcha/"); setCaptcha(data); } catch (e) { notify.fail(e); }
  };
  useEffect(() => { if (human && !captcha) void loadCaptcha(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [human]);

  const fieldText = (k: string, v: unknown) => {
    const m = String(Array.isArray(v) ? v[0] : v);
    if (m === "username_taken") return t("register.usernameTaken");
    if (k === "username") return t("register.usernameInvalid");
    return m;
  };

  const start = async (e: FormEvent) => {
    e.preventDefault();
    if (f.password !== f.confirm) return setErrors({ confirm: t("register.mismatch") });
    if (!human || !captcha) return setErrors({ captcha: t("register.robotRequired") });
    setBusy(true); setErrors({});
    try {
      await register({
        first_name: f.first_name, last_name: f.last_name, username: f.username.trim(), password: f.password,
        captcha_token: captcha.token, captcha_answer: answer, website: f.website,
      });
      nav("/", { replace: true });
    } catch (err) {
      const p = parseError(err);
      if (p.code === "captcha_invalid") setErrors({ captcha: t("errors.captcha_invalid") });
      else if (Object.keys(p.fields).length) setErrors(Object.fromEntries(Object.entries(p.fields).map(([k, v]) => [k, fieldText(k, v)])));
      else notify.fail(err);
      void loadCaptcha();  // a picture can be used only once
    } finally { setBusy(false); }
  };

  return (
    <AuthShell>
      <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">{t("register.title")}</h1>
      <p className="mt-1 text-sm text-slate-500">{t("register.subtitle")}</p>
      <form onSubmit={start} className="mt-6 space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label={t("common.firstName")} required value={f.first_name} error={errors.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} />
          <Input label={t("common.lastName")} required value={f.last_name} error={errors.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} />
        </div>
        <Input label={t("login.username")} required minLength={3} maxLength={150} value={f.username} error={errors.username} placeholder="ali_valiyev" hint={t("register.usernameHint")}
          autoComplete="username" autoCapitalize="none" spellCheck={false}
          onChange={(e) => setF({ ...f, username: e.target.value.replace(/\s/g, "") })} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label={t("login.password")} type="password" required autoComplete="new-password" value={f.password} error={errors.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
          <Input label={t("register.confirm")} type="password" required autoComplete="new-password" value={f.confirm} error={errors.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} />
        </div>
        <p className="text-xs text-slate-500">{t("profile.passwordHint")}</p>
        {/* honeypot: hidden from people, bots tend to fill it */}
        <input type="text" name="website" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} tabIndex={-1} autoComplete="off" aria-hidden="true"
          style={{ position: "absolute", left: "-9999px", width: 1, height: 1, opacity: 0 }} />

        <div className={`rounded-2xl border p-4 ${errors.captcha ? "border-red-300 bg-red-50/60" : "border-slate-200 bg-slate-50"}`}>
          <label className="flex cursor-pointer items-center gap-3">
            <input type="checkbox" checked={human} onChange={(e) => setHuman(e.target.checked)} className="h-6 w-6 rounded-md border-slate-300 text-blue-600" />
            <span className="font-medium text-slate-800">{t("register.notRobot")}</span>
            <span className="ml-auto text-xs text-slate-400">🛡️</span>
          </label>
          {human && (
            <div className="mt-4 space-y-3">
              <div className="flex items-center gap-3">
                {captcha ? <img src={captcha.image} alt={t("register.captchaAlt") as string} className="h-[70px] w-[210px] rounded-lg border border-slate-200 object-cover" />
                  : <div className="h-[70px] w-[210px] animate-pulse rounded-lg bg-slate-200" />}
                <button type="button" onClick={loadCaptcha} className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-white" title={t("register.newPicture") as string}>↻</button>
              </div>
              <Input label={t("register.captchaLabel")} value={answer} required maxLength={8} autoComplete="off" autoCapitalize="characters" spellCheck={false}
                onChange={(e) => setAnswer(e.target.value.toUpperCase())} style={{ letterSpacing: "0.3em", fontWeight: 700 }} />
            </div>
          )}
          {errors.captcha && <p className="mt-2 text-xs text-red-600">{errors.captcha}</p>}
        </div>

        <Button type="submit" loading={busy} className="w-full" size="lg" disabled={!human || answer.length < 4}>{t("register.submit")}</Button>
        <p className="text-center text-sm text-slate-500">{t("register.have")} <Link to="/login" className="font-semibold text-indigo-600 hover:underline">{t("login.submit")}</Link></p>
      </form>
    </AuthShell>
  );
}
