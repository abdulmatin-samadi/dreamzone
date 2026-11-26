import { useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, parseError } from "../api/client";
import type { Group } from "../api/types";
import { LevelBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Button, Card, EmptyState, Input, PageHeader, PageLoader } from "../components/ui";
import { useList } from "../lib/hooks";

/** A student joins a group with the code from the teacher and sees the groups they are in. */
export default function MyGroupPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const groups = useList<Group>("groups", {});
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const join = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setError("");
    try {
      const { data } = await api.post<Group>("/groups/join/", { code });
      setCode(""); notify.ok("myGroup.joined", { name: data.name });
      await qc.invalidateQueries();
    } catch (err) {
      const c = parseError(err).code;
      setError(t(`errors.${c}`, { defaultValue: t("errors.generic") }) as string);
    } finally { setBusy(false); }
  };

  const mine = groups.data?.results ?? [];
  return (
    <>
      <PageHeader title={t("nav.myGroup")} subtitle={t("myGroup.subtitle")} />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card title={t("myGroup.join")} className="lg:col-span-1">
          <form onSubmit={join} className="space-y-4">
            <Input label={t("myGroup.code")} value={code} error={error || undefined} placeholder="AB3K7P" maxLength={12} required
              onChange={(e) => setCode(e.target.value.toUpperCase())} autoCapitalize="characters" autoComplete="off" spellCheck={false}
              style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontWeight: 700, letterSpacing: "0.3em", fontSize: "1.125rem" }} hint={t("myGroup.codeHint")} />
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={code.trim().length < 4}>{t("myGroup.joinButton")}</Button>
          </form>
        </Card>
        <div className="space-y-4 lg:col-span-2">
          {groups.isLoading ? <PageLoader /> : mine.length === 0 ? <Card><EmptyState text={t("myGroup.none")} /></Card> : mine.map((g) => (
            <Card key={g.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t("myGroup.yourGroup")}</p>
                  <h2 className="mt-1 text-2xl font-bold text-slate-900">{g.name}</h2>
                </div>
                <LevelBadge code={g.level_code} />
              </div>
              <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-3">
                <div><dt className="text-slate-500">{t("groups.teacher")}</dt><dd className="mt-0.5 font-medium text-slate-900">{g.teacher_name ?? "—"}</dd></div>
                <div><dt className="text-slate-500">{t("groups.schedule")}</dt><dd className="mt-0.5 font-medium text-slate-900">{g.schedule || "—"}</dd></div>
                <div><dt className="text-slate-500">{t("myGroup.classmates")}</dt><dd className="mt-0.5 font-medium text-slate-900">{g.student_count}</dd></div>
              </dl>
            </Card>
          ))}
        </div>
      </div>
    </>
  );
}
