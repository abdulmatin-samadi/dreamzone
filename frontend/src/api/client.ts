import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from "axios";

const BASE = `${import.meta.env.VITE_API_URL ?? ""}/api/v1`;
const KEY = "dz_tokens";

export interface Tokens { access: string; refresh: string }

export const tokenStore = {
  get(): Tokens | null {
    try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch { return null; }
  },
  set(t: Tokens) { localStorage.setItem(KEY, JSON.stringify(t)); },
  clear() { localStorage.removeItem(KEY); },
};

/* ------------------------------------------------------------------ this device
 * A random id kept in this browser: the server ties a running test to one device and lists sign-ins per device.
 * The front desk may give the computer a name ("Kompyuter 3") so the live test list says where each test runs. */
const DEVICE_KEY = "dz_device_id";
const DEVICE_NAME_KEY = "dz_device_name";
let memoryDeviceId = "";

export function deviceId(): string {
  try {
    let id = localStorage.getItem(DEVICE_KEY) || "";
    if (!id) {
      id = (crypto.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`).replace(/[^A-Za-z0-9-]/g, "");
      localStorage.setItem(DEVICE_KEY, id);
    }
    return id;
  } catch {
    memoryDeviceId ||= `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    return memoryDeviceId;
  }
}
export function deviceName(): string {
  try { return localStorage.getItem(DEVICE_NAME_KEY) || ""; } catch { return ""; }
}
export function setDeviceName(name: string) {
  try { if (name.trim()) localStorage.setItem(DEVICE_NAME_KEY, name.trim().slice(0, 80)); else localStorage.removeItem(DEVICE_NAME_KEY); } catch { /* storage blocked */ }
}
function withDevice(cfg: InternalAxiosRequestConfig) {
  cfg.headers["X-Device-Id"] = deviceId();
  const name = deviceName();
  if (name) cfg.headers["X-Device-Name"] = encodeURIComponent(name);  // headers must stay ASCII
  return cfg;
}

export const api: AxiosInstance = axios.create({ baseURL: BASE });

api.interceptors.request.use((cfg: InternalAxiosRequestConfig) => {
  const t = tokenStore.get();
  if (t) cfg.headers.Authorization = `Bearer ${t.access}`;
  return withDevice(cfg);
});

let refreshing: Promise<string> | null = null;
let onAuthLost: () => void = () => {};
export const setAuthLostHandler = (fn: () => void) => { onAuthLost = fn; };

async function refreshAccess(): Promise<string> {
  const t = tokenStore.get();
  if (!t) throw new Error("no refresh token");
  const { data } = await axios.post(`${BASE}/auth/refresh/`, { refresh: t.refresh }, { headers: { "X-Device-Id": deviceId() } });
  tokenStore.set({ access: data.access, refresh: data.refresh ?? t.refresh });
  return data.access;
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const cfg = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    if (error.response?.status === 401 && cfg && !cfg._retry && tokenStore.get()) {
      cfg._retry = true;
      try {
        refreshing ??= refreshAccess().finally(() => { refreshing = null; });
        const access = await refreshing;
        cfg.headers.Authorization = `Bearer ${access}`;
        return api(cfg);
      } catch {
        tokenStore.clear();
        onAuthLost();
      }
    }
    return Promise.reject(error);
  },
);

/** API used by the walk-in student at the reception kiosk (restricted token, no refresh). */
export function makeKioskApi(token: string): AxiosInstance {
  const inst = axios.create({ baseURL: BASE });
  inst.interceptors.request.use((cfg) => { cfg.headers.Authorization = `Bearer ${token}`; return withDevice(cfg); });
  return inst;
}

export interface ApiErrorInfo { code: string; detail: string; fields: Record<string, string[] | string> }

export function parseError(e: unknown): ApiErrorInfo {
  const err = e as AxiosError<{ code?: string; detail?: string; errors?: Record<string, string[] | string> }>;
  const d = err.response?.data;
  if (!err.response) return { code: "network_error", detail: "Network error", fields: {} };
  return {
    code: d?.code ?? `http_${err.response.status}`,
    detail: d?.detail ?? "Error",
    fields: (d?.errors && typeof d.errors === "object" ? d.errors : {}) as Record<string, string[] | string>,
  };
}


export async function download(path: string, params: Record<string, unknown>, filename: string) {
  const res = await api.get(path, { params, responseType: "blob" });
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}
