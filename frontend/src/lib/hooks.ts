import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Paginated } from "../api/types";

export function useDebounced<T>(value: T, ms = 350): T {
  const [v, setV] = useState(value);
  useEffect(() => { const h = setTimeout(() => setV(value), ms); return () => clearTimeout(h); }, [value, ms]);
  return v;
}

type Params = Record<string, string | number | boolean | undefined | null>;
const clean = (p: Params) => Object.fromEntries(Object.entries(p).filter(([, v]) => v !== "" && v != null));

/** Paginated list endpoint. */
export function useList<T>(path: string, params: Params = {}, enabled = true) {
  return useQuery({
    queryKey: [path, clean(params)],
    queryFn: async () => (await api.get<Paginated<T>>(`/${path}/`, { params: clean(params) })).data,
    placeholderData: keepPreviousData,
    enabled,
  });
}

/** Un-paginated endpoint (levels, variants) or detail endpoint. */
export function useGet<T>(path: string, params: Params = {}, enabled = true) {
  return useQuery({
    queryKey: [path, clean(params)],
    queryFn: async () => (await api.get<T>(`/${path}/`, { params: clean(params) })).data,
    enabled,
  });
}

/** Lookup list helper: returns all rows (page_size=200) regardless of pagination. */
export function useAll<T>(path: string, params: Params = {}, enabled = true) {
  const q = useList<T>(path, { page_size: 200, ...params }, enabled);
  return { ...q, items: q.data?.results ?? [] };
}

export const fmtDate = (s: string | null | undefined, withTime = true) =>
  s ? new Date(s).toLocaleString(undefined, withTime
    ? { dateStyle: "medium", timeStyle: "short" } : { dateStyle: "medium" }) : "—";

export const toLocalInput = (s: string | null) => (s ? new Date(new Date(s).getTime() - new Date(s).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "");
export const fromLocalInput = (s: string) => (s ? new Date(s).toISOString() : null);
export const num = (v: string | number) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });
