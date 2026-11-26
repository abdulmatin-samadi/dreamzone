import { createContext, ReactNode, useCallback, useContext, useState } from "react";
import { useTranslation } from "react-i18next";

import { parseError } from "../api/client";

type Kind = "success" | "error";
interface Item { id: number; kind: Kind; text: string }
interface Notify { ok: (key: string, opts?: Record<string, unknown>) => void; fail: (e: unknown) => void }

const Ctx = createContext<Notify>(null as unknown as Notify);
export const useNotify = () => useContext(Ctx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Item[]>([]);

  const push = useCallback((kind: Kind, text: string) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { id, kind, text }]);
    setTimeout(() => setItems((s) => s.filter((i) => i.id !== id)), 4500);
  }, []);

  const value: Notify = {
    ok: (key, opts) => push("success", t(key, opts ?? {}) as string),
    fail: (e) => {
      const err = parseError(e);
      const msg = t(`errors.${err.code}`, { defaultValue: "" }) as string;
      if (msg) return push("error", msg);
      const first = Object.values(err.fields).flat()[0];
      push("error", typeof first === "string" ? first : (err.detail || (t("errors.generic") as string)));
    },
  };

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex w-[min(92vw,22rem)] flex-col gap-2" role="status" aria-live="polite">
        {items.map((i) => (
          <div key={i.id}
            className={`rounded-lg border px-4 py-3 text-sm shadow-lg ${i.kind === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-red-200 bg-red-50 text-red-800"}`}>
            {i.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
