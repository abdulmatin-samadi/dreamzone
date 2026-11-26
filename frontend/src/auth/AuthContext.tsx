import { useQueryClient } from "@tanstack/react-query";
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, setAuthLostHandler, tokenStore } from "../api/client";
import type { Role, User } from "../api/types";
import i18n from "../i18n";

/** Only admins and teachers get the bilingual dashboard; reception & students use Uzbek. */
export const BILINGUAL_ROLES: Role[] = ["ADMIN", "TEACHER", "RECEPTIONIST", "STUDENT"];

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<User>;
  /** step 2 of self-registration: the e-mailed code signs the new student in */
  register: (body: Record<string, string>) => Promise<User>;
  logout: () => Promise<void>;
  setLanguage: (lang: string) => Promise<void>;
  refreshUser: () => Promise<void>;
}

const Ctx = createContext<AuthState>(null as unknown as AuthState);
export const useAuth = () => useContext(Ctx);

function applyLanguage(user: User) {
  const lang = BILINGUAL_ROLES.includes(user.role) ? user.language : "uz";
  localStorage.setItem("dz_lang", lang);
  void i18n.changeLanguage(lang);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!tokenStore.get());

  const qc = useQueryClient();
  // cached pages belong to one account: never show them to the next one (e.g. a student's dashboard to a teacher)
  const clear = useCallback(() => { tokenStore.clear(); qc.clear(); setUser(null); }, [qc]);

  useEffect(() => {
    setAuthLostHandler(clear);
    if (!tokenStore.get()) return;
    api.get<User>("/auth/me/")
      .then((r) => { setUser(r.data); applyLanguage(r.data); })
      .catch(clear)
      .finally(() => setLoading(false));
  }, [clear]);

  const login = useCallback(async (username: string, password: string) => {
    const { data } = await api.post("/auth/login/", { username, password });
    tokenStore.set({ access: data.access, refresh: data.refresh });
    qc.clear();
    setUser(data.user);
    // a language picked on the login screen wins for admins / teachers and is saved to their profile
    const picked = sessionStorage.getItem("dz_lang_pick");
    sessionStorage.removeItem("dz_lang_pick");
    if (picked && picked !== data.user.language && BILINGUAL_ROLES.includes(data.user.role)) {
      try { const r = await api.patch<User>("/auth/me/", { language: picked }); data.user = r.data; setUser(r.data); } catch { /* keep the profile language */ }
    }
    applyLanguage(data.user);
    return data.user as User;
  }, [qc]);

  const register = useCallback(async (body: Record<string, string>) => {
    const { data } = await api.post("/auth/register/", body);
    tokenStore.set({ access: data.access, refresh: data.refresh });
    qc.clear();
    setUser(data.user);
    const picked = sessionStorage.getItem("dz_lang_pick");
    sessionStorage.removeItem("dz_lang_pick");
    if (picked && picked !== data.user.language) {
      try { const r = await api.patch<User>("/auth/me/", { language: picked }); data.user = r.data; setUser(r.data); } catch { /* keep the default language */ }
    }
    applyLanguage(data.user);
    return data.user as User;
  }, [qc]);

  const logout = useCallback(async () => {
    const t = tokenStore.get();
    try { if (t) await api.post("/auth/logout/", { refresh: t.refresh }); } catch { /* token already invalid */ }
    clear();
  }, [clear]);

  const setLanguage = useCallback(async (lang: string) => {
    await i18n.changeLanguage(lang);
    localStorage.setItem("dz_lang", lang);
    const { data } = await api.patch<User>("/auth/me/", { language: lang }); // persisted in the user profile
    setUser(data);
  }, []);

  const refreshUser = useCallback(async () => {
    const { data } = await api.get<User>("/auth/me/");
    setUser(data);
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout, setLanguage, refreshUser }),
    [user, loading, login, register, logout, setLanguage, refreshUser]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
