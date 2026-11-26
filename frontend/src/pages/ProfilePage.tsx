import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, parseError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Badge, Button, Card, Input, PageHeader } from "../components/ui";
import { MySessions } from "../components/Sessions";
import { useNotify } from "../components/Toast";

export default function ProfilePage() {
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();
  const notify = useNotify();
  const [form, setForm] = useState({ first_name: user!.first_name, last_name: user!.last_name, phone: user!.phone, email: user!.email });
  const [pw, setPw] = useState({ old_password: "", new_password: "" });
  const [login, setLogin] = useState({ username: "", password: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  // server messages -> the user's language
  const known: Record<string, string> = {
    "Wrong password.": "profile.wrongPassword", "This login is already taken.": "profile.loginTaken",
  };
  const fieldErrors = (err: unknown, prefix: string) => {
    const f = parseError(err).fields as Record<string, unknown>;
    const out: Record<string, string> = {};
    for (const [k, v] of Object.entries(f)) {
      const msg = String(Array.isArray(v) ? v[0] : v);
      out[`${prefix}.${k}`] = known[msg] ? t(known[msg]) : k === "username" ? t("profile.loginInvalid") : msg;
    }
    setErrs(out);
    if (!Object.keys(out).length) notify.fail(err);
  };
  const [busy, setBusy] = useState(false);

  const save = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true);
    try { await api.patch("/auth/me/", form); await refreshUser(); notify.ok("common.saved"); } catch (err) { notify.fail(err); } finally { setBusy(false); }
  };
  const changePw = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true);
    setErrs({});
    try { await api.post("/auth/change-password/", pw); setPw({ old_password: "", new_password: "" }); notify.ok("profile.passwordChanged"); } catch (err) { fieldErrors(err, "pw"); } finally { setBusy(false); }
  };
  const changeLogin = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErrs({});
    try {
      await api.post("/auth/change-username/", { username: login.username.trim(), password: login.password });
      setLogin({ username: "", password: "" }); await refreshUser(); notify.ok("profile.loginChanged");
    } catch (err) { fieldErrors(err, "login"); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={t("nav.profile")} />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title={t("profile.details")}>
          <p className="mb-4 text-sm text-slate-500">{user!.username} · <Badge tone="indigo">{t(`roles.${user!.role}`)}</Badge>{user!.current_level && <> · <Badge>{user!.current_level}</Badge></>}</p>
          <form onSubmit={save} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Input label={t("common.firstName")} value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} required />
              <Input label={t("common.lastName")} value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} required />
            </div>
            <Input label={t("common.phone")} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            <Input label="Email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <Button type="submit" loading={busy}>{t("common.save")}</Button>
          </form>
        </Card>
        <div className="space-y-6">
          <Card title={t("profile.changeLogin")}>
            <p className="mb-4 text-sm text-slate-600">{t("profile.currentLogin")}: <code className="rounded bg-slate-100 px-2 py-0.5 font-semibold text-slate-900">{user!.username}</code></p>
            <form onSubmit={changeLogin} className="space-y-4">
              <Input label={t("profile.newLogin")} hint={t("profile.loginHint")} value={login.username} error={errs["login.username"]}
                onChange={(e) => setLogin({ ...login, username: e.target.value })} autoComplete="username" autoCapitalize="off" spellCheck={false} required minLength={3} maxLength={150} />
              <Input label={t("profile.oldPassword")} type="password" value={login.password} error={errs["login.password"]}
                onChange={(e) => setLogin({ ...login, password: e.target.value })} autoComplete="current-password" required />
              <Button type="submit" loading={busy}>{t("profile.changeLogin")}</Button>
            </form>
          </Card>
          <Card title={t("profile.changePassword")}>
            <form onSubmit={changePw} className="space-y-4">
              <Input label={t("profile.oldPassword")} type="password" value={pw.old_password} error={errs["pw.old_password"]} onChange={(e) => setPw({ ...pw, old_password: e.target.value })} autoComplete="current-password" required />
              <Input label={t("profile.newPassword")} type="password" hint={t("profile.passwordHint")} value={pw.new_password} error={errs["pw.new_password"]} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} autoComplete="new-password" required />
              <Button type="submit" loading={busy}>{t("profile.changePassword")}</Button>
            </form>
          </Card>
        </div>
        <div className="lg:col-span-2"><MySessions /></div>
      </div>
    </>
  );
}
