import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "../api/client";
import type { User } from "../api/types";
import { fmtDate } from "../lib/hooks";
import { useNotify } from "./Toast";
import { Badge, Button, Card, ConfirmDialog, EmptyState, Modal, PageLoader } from "./ui";

export interface SessionRow { id: string; device: string; device_name: string; ip: string | null; created_at: string; last_seen_at: string; current: boolean }

const icon = (d: string) => (/iPhone|Android/.test(d) ? "📱" : /iPad/.test(d) ? "📲" : "💻");

function SessionList({ rows, onRevoke, busy }: { rows: SessionRow[]; onRevoke?: (s: SessionRow) => void; busy?: string | null }) {
  const { t } = useTranslation();
  if (!rows.length) return <EmptyState text={t("sessions.none")} />;
  return (
    <ul className="divide-y divide-slate-100">
      {rows.map((s) => (
        <li key={s.id} className="flex items-center justify-between gap-3 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <span className="text-2xl" aria-hidden>{icon(s.device)}</span>
            <div className="min-w-0 text-sm">
              <p className="flex flex-wrap items-center gap-2 font-medium text-slate-900">
                {[s.device_name, s.device].filter(Boolean).join(" — ") || t("sessions.unknown")}
                {s.current && <Badge tone="green">{t("sessions.current")}</Badge>}
              </p>
              <p className="text-xs text-slate-500">{t("sessions.lastSeen")}: {fmtDate(s.last_seen_at)} · {t("sessions.since")}: {fmtDate(s.created_at, false)}{s.ip && ` · ${s.ip}`}</p>
            </div>
          </div>
          {onRevoke && !s.current && <Button size="sm" variant="ghost" loading={busy === s.id} onClick={() => onRevoke(s)}>{t("sessions.signOut")}</Button>}
        </li>
      ))}
    </ul>
  );
}

/** Profile: the devices I am signed in on; sign one out or all the others. */
export function MySessions() {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["sessions"], queryFn: async () => (await api.get<SessionRow[]>("/auth/sessions/")).data });
  const [busy, setBusy] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const revoke = async (s: SessionRow) => {
    setBusy(s.id);
    try { await api.post(`/auth/sessions/${s.id}/revoke/`); notify.ok("sessions.signedOutOne"); await qc.invalidateQueries({ queryKey: ["sessions"] }); }
    catch (e) { notify.fail(e); } finally { setBusy(null); }
  };
  const revokeOthers = async () => {
    setBusy("all");
    try { const { data } = await api.post<{ revoked: number }>("/auth/sessions/revoke-others/"); notify.ok("sessions.signedOutN", { n: data.revoked }); await qc.invalidateQueries({ queryKey: ["sessions"] }); }
    catch (e) { notify.fail(e); } finally { setBusy(null); setConfirm(false); }
  };
  const others = (q.data ?? []).filter((s) => !s.current).length;
  return (
    <Card title={t("sessions.title")} actions={others > 0 && <Button size="sm" variant="danger" onClick={() => setConfirm(true)}>{t("sessions.signOutOthers")}</Button>}>
      <p className="mb-2 text-sm text-slate-500">{t("sessions.hint")}</p>
      {!q.data ? <PageLoader /> : <SessionList rows={q.data} onRevoke={revoke} busy={busy} />}
      <ConfirmDialog open={confirm} danger loading={busy === "all"} title={t("sessions.signOutOthers")} message={t("sessions.signOutOthersConfirm", { n: others })}
        confirmLabel={t("sessions.signOutOthers")} onConfirm={revokeOthers} onClose={() => setConfirm(false)} />
    </Card>
  );
}

/** Admin: one user's devices, and "sign out everywhere". */
export function UserSessionsModal({ user, onClose }: { user: User | null; onClose: () => void }) {
  const { t } = useTranslation();
  const notify = useNotify();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["user-sessions", user?.id], enabled: !!user, queryFn: async () => (await api.get<SessionRow[]>(`/users/${user!.id}/sessions/`)).data });
  const [busy, setBusy] = useState(false);
  const all = async () => {
    setBusy(true);
    try { const { data } = await api.post<{ revoked: number }>(`/users/${user!.id}/logout-all/`); notify.ok("sessions.signedOutN", { n: data.revoked }); await qc.invalidateQueries({ queryKey: ["user-sessions"] }); }
    catch (e) { notify.fail(e); } finally { setBusy(false); }
  };
  return (
    <Modal open={!!user} onClose={onClose} title={user ? t("sessions.adminTitle", { name: user.full_name }) : ""}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.close")}</Button>
        <Button variant="danger" loading={busy} disabled={!q.data?.length} onClick={all}>{t("sessions.logoutAll")}</Button></>}>
      {!q.data ? <PageLoader /> : <SessionList rows={q.data} />}
    </Modal>
  );
}
