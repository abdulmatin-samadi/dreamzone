import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./locales/en";
import uz from "./locales/uz";

/** To add a language: create `locales/<code>.ts` with the same keys and register it here. */
export const LANGUAGES = [
  { code: "uz", label: "O'zbekcha" },
  { code: "en", label: "English" },
] as const;

export const resources = { uz: { translation: uz }, en: { translation: en } };

i18n.use(initReactI18next).init({
  resources,
  lng: localStorage.getItem("dz_lang") || "uz",
  fallbackLng: "uz",
  interpolation: { escapeValue: false },
});

export default i18n;
