import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { parseError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AuthShell } from "../components/AuthShell";
import { Button, Input } from "../components/ui";

export default function LoginPage() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError("");
    try { await login(username.trim(), password); nav("/", { replace: true }); }
    catch (err) {
      const p = parseError(err);
      setError(p.code === "no_active_account" || p.code === "http_401" ? t("login.invalid") : t(`errors.${p.code}`, { defaultValue: t("errors.generic") }));
    } finally { setBusy(false); }
  };

  return (
    <AuthShell>
      <h1 className="text-3xl font-extrabold tracking-tight text-slate-900">{t("login.title")}</h1>
      <p className="mt-1 text-sm text-slate-500">{t("login.subtitle")}</p>
      <form onSubmit={submit} className="mt-7 space-y-5">
        {error && <div className="rounded-xl bg-red-50 px-4 py-3 text-sm text-red-700 ring-1 ring-red-200" role="alert">{error}</div>}
        <Input label={t("login.username")} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required placeholder={t("login.usernamePh") as string} />
        <div className="relative">
          <Input label={t("login.password")} type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required placeholder="••••••••" />
          <button type="button" onClick={() => setShow(!show)} className="absolute bottom-2 right-3 text-xs font-medium text-indigo-600 hover:underline">{show ? t("login.hide") : t("login.show")}</button>
        </div>
        <Button type="submit" loading={busy} className="w-full" size="lg">{t("login.submit")}</Button>
      </form>
      <div className="my-6 flex items-center gap-3 text-xs text-slate-400"><span className="h-px flex-1 bg-slate-200" />{t("login.or")}<span className="h-px flex-1 bg-slate-200" /></div>
      <Link to="/register" className="block rounded-xl border border-sky-200 bg-sky-50/70 px-4 py-3 text-center text-sm text-slate-600 transition hover:bg-sky-100">
        {t("login.newHere")} <span className="font-semibold text-indigo-700">{t("login.registerLink")} →</span>
      </Link>
    </AuthShell>
  );
}
