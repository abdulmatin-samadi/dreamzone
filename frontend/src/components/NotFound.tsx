import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button, Card } from "./ui";

/** Shown when a detail request fails (404 / no access) instead of an endless spinner. */
export function LoadError() {
  const { t } = useTranslation();
  const nav = useNavigate();
  return (
    <Card className="mx-auto mt-10 max-w-md text-center">
      <p className="text-lg font-semibold">{t("errors.not_found")}</p>
      <p className="mt-1 text-sm text-slate-500">{t("errors.notFoundHint")}</p>
      <Button className="mt-4" onClick={() => nav(-1)}>{t("common.back")}</Button>
    </Card>
  );
}
