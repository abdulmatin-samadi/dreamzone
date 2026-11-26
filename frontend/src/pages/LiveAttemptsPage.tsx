import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { api, deviceName, setDeviceName } from "../api/client";
import { LevelBadge } from "../components/badges";
import { StoppedAttempts } from "../components/StoppedAttempts";
import { useNotify } from "../components/Toast";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Input, PageHeader, PageLoader, ProgressBar, cx } from "../components/ui";

interface Live {
  id: number; student: string; student_id: number; is_guest: boolean; examination: string; level: string; kind: string;
  status: "IN_PROGRESS" | "PENDING_TEACHER_APPROVAL"; started_at: string; deadline_at: string; remaining_seconds: number;
  answered: number; total: number; device: string; last_seen_at: string | null; online: boolean; violation: boolean;
}

const clock = (s: number) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

/** Who is sitting which test on which computer right now (refreshes every 5 s; the clock ticks every second). */
export default function LiveAttemptsPage() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["live-attempts"], refetchInterval: 5000,
    queryFn: async () => {
      const { data } = await api.get<{ server_time: string; attempts: Live[] }>("/live-attempts/");
      return { ...data, fetched: Date.now() };
    },
  });
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const h = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(h); }, []);
  const [name, setName] = useState(deviceName());
  const [release, setRelease] = useState<Live | null>(null);
  const [busy, setBusy] = useState(false);

  const saveName = (e: FormEvent) => { e.preventDefault(); setDeviceName(name); setName(deviceName()); notify.ok("live.nameSaved"); };
  const doRelease = async () => {
    setBusy(true);
    try { await api.post(`/live-attempts/${release!.id}/release-device/`); notify.ok("live.released"); await qc.invalidateQueries({ queryKey: ["live-attempts"] }); }
    catch (e) { notify.fail(e); } finally { setBusy(false); setRelease(null); }
  };

  const rows = (q.data?.attempts ?? []).filter((r) => r.status === "IN_PROGRESS");  // stopped ones are in the card above
  const since = q.data ? Math.floor((now - q.data.fetched) / 1000) : 0;  // seconds since the last refresh

  return (
    <>
      <PageHeader title={t("live.title")} subtitle={t("live.subtitle")}
        actions={<Badge tone={rows.length ? "green" : "gray"}>{t("live.running", { n: rows.length })}</Badge>} />
      <StoppedAttempts />
      {!q.data ? <PageLoader /> : rows.length === 0 ? <Card><EmptyState text={t("live.empty")} /></Card> : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((a) => {
            const paused = a.status !== "IN_PROGRESS";
            const left = paused ? a.remaining_seconds : Math.max(0, a.remaining_seconds - since);
            const seenAgo = a.last_seen_at ? Math.max(0, Math.round((now - new Date(a.last_seen_at).getTime()) / 1000)) : null;
            const online = !paused && seenAgo !== null && seenAgo <= 45;
            const pct = a.total ? Math.round((a.answered / a.total) * 100) : 0;
            return (
              <Card key={a.id} className={cx(a.violation && "border-red-400", paused && "border-amber-300")}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-900">{a.student}</p>
                    <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                      <LevelBadge code={a.level} /> <span className="truncate">{a.examination}</span>
                      {a.is_guest && <Badge tone="amber">{t("live.guest")}</Badge>}
                    </p>
                  </div>
                  <div className={cx("shrink-0 rounded-lg px-2.5 py-1 font-mono text-lg font-bold tabular-nums",
                    paused ? "bg-amber-50 text-amber-700" : left < 300 ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-800")}
                    title={t("live.left")}>{clock(left)}</div>
                </div>
                <div className="mt-4 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-slate-700" title={a.device}>🖥 {a.device || t("live.unknownDevice")}</span>
                    {paused ? <Badge tone="amber">{t("live.paused")}</Badge>
                      : <span className={cx("inline-flex shrink-0 items-center gap-1.5 text-xs font-medium", online ? "text-emerald-700" : "text-slate-500")}>
                        <span className={cx("h-2 w-2 rounded-full", online ? "bg-emerald-500" : "bg-slate-400")} />
                        {online ? t("live.online") : seenAgo === null ? t("live.offline") : t("live.lastSeen", { s: seenAgo })}
                      </span>}
                  </div>
                </div>
                {a.violation && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">⚠ {t("live.violation")}</p>}
                <div className="mt-4">
                  <div className="mb-1 flex justify-between text-xs text-slate-500"><span>{t("live.progress")}</span><span>{a.answered} / {a.total}</span></div>
                  <ProgressBar value={pct} />
                </div>
                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                  <span className="whitespace-nowrap">{t("live.started")}: {new Date(a.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                  {a.device && <Button size="sm" variant="ghost" className="whitespace-nowrap" onClick={() => setRelease(a)}>{t("live.release")}</Button>}
                </div>
              </Card>
            );
          })}
        </div>
      )}
      <Card title={t("live.thisComputer")} className="mt-6">
        <form onSubmit={saveName} className="flex flex-wrap items-end gap-3">
          <Input className="min-w-0 flex-1 sm:max-w-sm" label={t("live.computerName")} hint={t("live.thisComputerHint")} value={name} maxLength={80}
            placeholder={t("live.computerPh") as string} onChange={(e) => setName(e.target.value)} />
          <Button type="submit" variant="secondary">{t("common.save")}</Button>
        </form>
      </Card>
      <ConfirmDialog open={!!release} loading={busy} title={t("live.release")} confirmLabel={t("live.release")}
        message={t("live.releaseConfirm", { name: release?.student, device: release?.device })} onConfirm={doRelease} onClose={() => setRelease(null)} />
    </>
  );
}
