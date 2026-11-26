import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import type { Assignment, Exam, Level, Student } from "../api/types";
import { LevelBadge, StateBadge } from "../components/badges";
import { useNotify } from "../components/Toast";
import { Badge, Button, Card, EmptyState, Input, Modal, PageHeader, Pagination, SearchInput, Select, Table, Td } from "../components/ui";
import { fmtDate, useAll, useGet, useList } from "../lib/hooks";
import { enterFullscreen } from "../components/ExamRunner";
import { StoppedAttempts } from "../components/StoppedAttempts";
import { openKiosk } from "./KioskPage";

export default function PlacementsPage() {
  const { user } = useAuth();
  const { t } = useTranslation();
  const notify = useNotify();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [studentSearch, setStudentSearch] = useState("");
  const [selected, setSelected] = useState<Student | null>(null);
  const [level, setLevel] = useState("");
  const [busy, setBusy] = useState<number | "assign" | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [quick, setQuick] = useState({ level: "", first_name: "", last_name: "" });
  const [enroll, setEnroll] = useState<Assignment | null>(null);
  const [ef, setEf] = useState({ first_name: "", last_name: "", phone: "" });
  const [creds, setCreds] = useState<{ username: string; password: string } | null>(null);

  const levels = useGet<Level[]>("levels");
  const exams = useAll<Exam>("examinations", { kind: "PLACEMENT" });
  const found = useList<Student>("students", { search: studentSearch, page_size: 6 }, studentSearch.length >= 2);
  const list = useList<Assignment>("placements", { search, page });

  const readyLevels = new Set(exams.items.filter((e) => e.status === "PUBLISHED").map((e) => e.level));
  const refresh = () => void qc.invalidateQueries({ queryKey: ["placements"] });

  const startQuick = async () => {
    await enterFullscreen();   // needs the click that started the test
    setBusy("assign");
    try {
      const { data } = await api.post<{ attempt_id: number; kiosk_token: string; student_name: string }>("/placements/quick/", { level: Number(quick.level), first_name: quick.first_name, last_name: quick.last_name });
      openKiosk(nav, { token: data.kiosk_token, attemptId: data.attempt_id, studentName: data.student_name });
    } catch (e) { notify.fail(e); setBusy(null); }
  };
  const doEnroll = async () => {
    setBusy("assign");
    try {
      const { data } = await api.post<{ username: string; password: string }>(`/students/${enroll!.student}/enroll/`, ef);
      setCreds(data); setEnroll(null); refresh(); void qc.invalidateQueries({ queryKey: ["students"] });
    } catch (e) { notify.fail(e); } finally { setBusy(null); }
  };

  const pick = (s: Student) => { setSelected(s); setLevel(String(s.initial_level ?? "")); setStudentSearch(""); };

  const start = async (a: Assignment) => {
    if (!document.fullscreenElement) await enterFullscreen();
    setBusy(a.id);
    try {
      const { data } = await api.post<{ attempt_id: number; kiosk_token: string; student_name: string }>(`/placements/${a.id}/start/`);
      openKiosk(nav, { token: data.kiosk_token, attemptId: data.attempt_id, studentName: data.student_name });
    } catch (e) { notify.fail(e); setBusy(null); }
  };

  const assign = async (startNow: boolean) => {
    if (!selected || !level) return;
    if (startNow) await enterFullscreen();
    setBusy("assign");
    try {
      const { data } = await api.post<Assignment>("/placements/", { student: selected.id, level: Number(level) });
      notify.ok("placements.assigned");
      setSelected(null); setLevel(""); refresh();
      if (startNow) await start(data);
    } catch (e) { notify.fail(e); } finally { setBusy(null); }
  };

  return (
    <>
      <PageHeader title={t("nav.placements")} subtitle={t("placements.subtitle")} />
      <StoppedAttempts />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
        <Card title={t("placements.quickTitle")}>
          <p className="mb-4 text-sm text-slate-500">{t("placements.quickHint")}</p>
          <div className="space-y-4">
            <Select label={t("placements.level")} required value={quick.level} onChange={(e) => setQuick({ ...quick, level: e.target.value })}>
              <option value="">—</option>
              {levels.data?.filter((l) => l.is_active).map((l) => <option key={l.id} value={l.id} disabled={!readyLevels.has(l.id)}>{l.code} — {l.name}{readyLevels.has(l.id) ? "" : ` (${t("placements.notReady")})`}</option>)}
            </Select>
            <div className="grid grid-cols-2 gap-3">
              <Input label={`${t("common.firstName")} (${t("common.optional")})`} value={quick.first_name} onChange={(e) => setQuick({ ...quick, first_name: e.target.value })} />
              <Input label={`${t("common.lastName")} (${t("common.optional")})`} value={quick.last_name} onChange={(e) => setQuick({ ...quick, last_name: e.target.value })} />
            </div>
            <Button size="lg" className="w-full" disabled={!quick.level} loading={busy === "assign"} onClick={startQuick}>{t("placements.quickStart")}</Button>
          </div>
        </Card>
        <Card title={t("placements.newTitle")}>
          <div className="space-y-4">
            {!selected ? (
              <>
                <SearchInput value={studentSearch} onChange={setStudentSearch} placeholder={t("students.searchPlaceholder")} />
                {studentSearch.length >= 2 && (found.data?.results.length ? (
                  <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
                    {found.data.results.map((s) => (
                      <li key={s.id}><button className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => pick(s)}>
                        <span><b>{s.full_name}</b><br /><span className="text-xs text-slate-500">{s.phone}</span></span><LevelBadge code={s.initial_level_code} /></button></li>
                    ))}
                  </ul>
                ) : <EmptyState />)}
                {user!.role === "ADMIN" ? <Link to="/students" className="block text-sm text-indigo-600 hover:underline">{t("placements.notFound")}</Link>
                  : <p className="text-sm text-slate-500">{t("placements.notFoundSelf")}</p>}
              </>
            ) : (
              <>
                <div className="flex items-start justify-between rounded-lg bg-slate-50 p-3 text-sm">
                  <span><b>{selected.full_name}</b><br /><span className="text-slate-500">{selected.phone}</span></span>
                  <button className="text-xs text-indigo-600" onClick={() => setSelected(null)}>{t("common.change")}</button>
                </div>
                <Select label={t("placements.level")} value={level} onChange={(e) => setLevel(e.target.value)}>
                  <option value="">—</option>
                  {levels.data?.filter((l) => l.is_active).map((l) => <option key={l.id} value={l.id} disabled={!readyLevels.has(l.id)}>{l.code} — {l.name}{readyLevels.has(l.id) ? "" : ` (${t("placements.notReady")})`}</option>)}
                </Select>
                <div className="flex flex-wrap gap-2">
                  <Button disabled={!level} loading={busy === "assign"} onClick={() => assign(true)}>{t("placements.assignStart")}</Button>
                  <Button variant="secondary" disabled={!level || busy === "assign"} onClick={() => assign(false)}>{t("placements.assignOnly")}</Button>
                </div>
              </>
            )}
          </div>
        </Card>
        </div>

        <div className="lg:col-span-2">
          <div className="mb-3"><SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder={t("students.searchPlaceholder")} /></div>
          <Table head={[t("common.student"), t("placements.level"), t("result.status"), t("common.date"), ""]} empty={!list.data?.results.length}>
            {list.data?.results.map((a) => (
              <tr key={a.id}>
                <Td className="font-medium">{a.student_name} {a.student_is_guest && <Badge tone="amber">{t("placements.guest")}</Badge>}</Td>
                <Td><LevelBadge code={a.level_code} /></Td>
                <Td><StateBadge state={a.state} /></Td>
                <Td className="whitespace-nowrap">{fmtDate(a.created_at)}</Td>
                <Td className="text-right">
                  {(a.state === "available" || a.state === "in_progress") && <Button size="sm" loading={busy === a.id} onClick={() => start(a)}>{a.state === "in_progress" ? t("exam.continue") : t("placements.startExam")}</Button>}
                  {a.state === "completed" && a.result_id && <Link to={`/results/${a.result_id}`}><Button size="sm" variant="secondary">{t("myExams.viewResult")}</Button></Link>}
                  {user!.role === "ADMIN" && a.student_is_guest && a.state === "completed" && <Button size="sm" variant="ghost" onClick={() => { setEnroll(a); setEf({ first_name: "", last_name: "", phone: "" }); }}>{t("placements.enroll")}</Button>}
                  {a.state === "expired" && <Badge tone="red">{t("states.expired")}</Badge>}
                </Td>
              </tr>
            ))}
          </Table>
          <Pagination page={page} count={list.data?.count ?? 0} onPage={setPage} />
        </div>
      </div>
      <Modal open={!!enroll} onClose={() => setEnroll(null)} title={t("placements.enroll")}
        footer={<><Button variant="secondary" onClick={() => setEnroll(null)}>{t("common.cancel")}</Button><Button loading={busy === "assign"} disabled={!ef.first_name || !ef.last_name || ef.phone.length < 7} onClick={doEnroll}>{t("common.save")}</Button></>}>
        <p className="mb-3 text-sm text-slate-600">{t("placements.enrollHint")}</p>
        <div className="space-y-3">
          <Input label={t("common.firstName")} value={ef.first_name} onChange={(e) => setEf({ ...ef, first_name: e.target.value })} />
          <Input label={t("common.lastName")} value={ef.last_name} onChange={(e) => setEf({ ...ef, last_name: e.target.value })} />
          <Input label={t("common.phone")} value={ef.phone} onChange={(e) => setEf({ ...ef, phone: e.target.value })} />
        </div>
      </Modal>
      <Modal open={!!creds} onClose={() => setCreds(null)} title={t("students.credentials")} footer={<Button onClick={() => setCreds(null)}>{t("common.close")}</Button>}>
        <dl className="space-y-2 rounded-lg bg-slate-50 p-4 font-mono text-sm"><div>{creds?.username}</div><div className="text-lg font-semibold">{creds?.password}</div></dl>
        <p className="mt-3 text-xs text-amber-700">{t("students.shownOnce")}</p>
      </Modal>
    </>
  );
}
