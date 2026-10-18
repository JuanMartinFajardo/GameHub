// SPDX-License-Identifier: AGPL-3.0-or-later
/** La moderación del hub: denuncias, ocultar repositorios y suspender cuentas. */

import { useMessages } from "@gamehub/i18n";
import { Link } from "@gamehub/shell";
import { Button, Panel } from "@gamehub/ui-kit";
import { useState } from "react";
import { errorText, get, post } from "../api";
import { messages } from "../messages";
import { useSession } from "../session";
import { Loading, useLoad, When } from "../ui";

interface Report {
  id: number;
  target: string;
  label: string;
  reason: string;
  reporter: string | null;
  status: string;
  resolution: string;
  created: number;
}

export function AdminPage() {
  const t = useMessages(messages);
  const { user } = useSession();
  const [status, setStatus] = useState("open");
  const reports = useLoad(user?.admin ? status : null, () =>
    get<{ reports: Report[] }>(`/admin/reports?status=${status}`),
  );
  const [error, setError] = useState<string | null>(null);
  if (!user?.admin) return <p className="gh-shell-error">{t("adminOnly")}</p>;
  const act = (work: Promise<unknown>) =>
    work.then(reports.reload).catch((e: unknown) => setError(errorText(e)));
  return (
    <div className="gh-shell-page">
      <h1>{t("moderation")}</h1>
      <p>
        <select className="gh-select" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="open">{t("reportsOpen")}</option>
          <option value="resolved">{t("reportsResolved")}</option>
          <option value="dismissed">{t("reportsDismissed")}</option>
        </select>
      </p>
      {error && <p className="gh-shell-error">{error}</p>}
      {reports.data ? (
        reports.data.reports.length ? (
          reports.data.reports.map((r) => {
            const [kind] = r.target.split(":");
            return (
              <Panel
                key={r.id}
                title={
                  <>
                    #{r.id} ·{" "}
                    {kind === "repo" || kind === "account" ? (
                      <Link to={`/${r.label}`}>{r.label}</Link>
                    ) : (
                      r.label
                    )}
                  </>
                }
              >
                <p>{r.reason}</p>
                <p className="gh-muted">
                  {r.reporter ?? t("anonymous")} · <When time={r.created} />
                  {r.resolution && ` · ${r.resolution}`}
                </p>
                {r.status === "open" && (
                  <p className="hub-actions">
                    {kind === "repo" && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() =>
                          act(
                            post(`/admin/repos/${r.label}`, { hidden: true }).then(() =>
                              post(`/admin/reports/${r.id}`, {
                                status: "resolved",
                                resolution: t("repoHidden"),
                              }),
                            ),
                          )
                        }
                      >
                        {t("hideRepo")}
                      </Button>
                    )}
                    {kind === "account" && (
                      <Button
                        variant="danger"
                        size="sm"
                        onClick={() =>
                          act(
                            post(`/admin/accounts/${r.label}`, { suspended: true }).then(() =>
                              post(`/admin/reports/${r.id}`, {
                                status: "resolved",
                                resolution: t("accountSuspended"),
                              }),
                            ),
                          )
                        }
                      >
                        {t("suspend")}
                      </Button>
                    )}
                    <Button
                      size="sm"
                      onClick={() => act(post(`/admin/reports/${r.id}`, { status: "dismissed" }))}
                    >
                      {t("dismiss")}
                    </Button>
                  </p>
                )}
              </Panel>
            );
          })
        ) : (
          <p className="gh-muted">{t("noReports")}</p>
        )
      ) : (
        <Loading error={reports.error} />
      )}
    </div>
  );
}
