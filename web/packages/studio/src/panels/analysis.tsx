// SPDX-License-Identifier: Apache-2.0
/**
 * La pestaña «Análisis»: teoría de juegos sobre el texto actual (`gamehub/analyze`, F7). El
 * asesor de viabilidad dice qué se puede calcular; cada botón pide un análisis y los resultados se
 * acumulan: la matriz de pagos con las mejores respuestas y los equilibrios, la solución de los
 * juegos de información perfecta, la estrategia de equilibrio por conjunto de información, la
 * convergencia de CFR, Grundy, la función característica y el torneo de Axelrod.
 */

import { useLocale, useMessages } from "@gamehub/i18n";
import { Badge, Button, cx, Spinner } from "@gamehub/ui-kit";
import { useState } from "react";
import { useStudio } from "../context";
import { type MessageKey, messages } from "../messages";
import type { PolicyRow, TheoryNumber, TheoryReport } from "../types";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Cada botón y los análisis que pide al servidor. */
export const THEORY_ACTIONS: { key: string; label: MessageKey; analyses: string[] }[] = [
  { key: "feasibility", label: "thFeasibility", analyses: ["feasibility"] },
  { key: "solve", label: "thSolve", analyses: ["count", "solve"] },
  {
    key: "nash",
    label: "thNash",
    analyses: ["normal_form", "nash", "dominance", "correlated", "pareto"],
  },
  { key: "sequence", label: "thSequence", analyses: ["tree", "sequence_form"] },
  { key: "cfr", label: "thCfr", analyses: ["cfr"] },
  { key: "grundy", label: "thGrundy", analyses: ["grundy"] },
  { key: "coop", label: "thCoop", analyses: ["normal_form", "coop"] },
  { key: "tournament", label: "thTournament", analyses: ["tournament"] },
];

/** La acción que ejecuta cada recomendación del asesor (las de fases futuras no tienen). */
const RECOMMENDATION_ACTION: Record<string, string> = {
  solve: "solve",
  grundy: "grundy",
  normal_form: "nash",
  nash: "nash",
  sequence_form: "sequence",
  cfr: "cfr",
  tournament: "tournament",
};

/** Un número del informe en texto: los racionales tal cual; los aproximados, con 4 cifras. */
export function fmt(x: TheoryNumber | null | undefined): string {
  if (x === null || x === undefined) return "—";
  if (typeof x === "string") return x;
  if (Number.isInteger(x)) return String(x);
  return Math.abs(x) < 1e-3 && x !== 0 ? x.toExponential(2) : x.toPrecision(4);
}

/** El valor numérico de un número del informe (los racionales "a/b" incluidos). */
export function value(x: TheoryNumber): number {
  if (typeof x === "number") return x;
  const [a, b] = x.split("/");
  return Number(a) / (b === undefined ? 1 : Number(b));
}

const profileName = (strategies: string[][], profile: number[]) =>
  `(${profile.map((s, k) => strategies[k]?.[s] ?? s).join(", ")})`;

export function AnalysisPanel() {
  const t = useMessages(messages) as T;
  const [state, studio] = useStudio();
  const [iterations, setIterations] = useState(1000);
  const [rounds, setRounds] = useState(200);
  const report = state.theory;
  const running = state.theoryRunning.length > 0;
  const compiled = !!state.analysis?.compiled;
  const run = (key: string) => {
    const action = THEORY_ACTIONS.find((a) => a.key === key);
    if (!action) return;
    studio.runTheory(action.analyses, { cfrIterations: iterations, tournamentRounds: rounds });
  };
  return (
    <div className="gh-sd-theory">
      <div className="gh-sd-row">
        <Button
          size="sm"
          variant="primary"
          disabled={!compiled || running}
          onClick={() => studio.runTheory(["auto"], { cfrIterations: iterations })}
        >
          {t("analyze")}
        </Button>
        {THEORY_ACTIONS.map((a) => (
          <Button key={a.key} size="sm" disabled={!compiled || running} onClick={() => run(a.key)}>
            {t(a.label)}
          </Button>
        ))}
        <label className="gh-sd-inline">
          {t("thIterations")}
          <input
            type="number"
            className="gh-sd-input gh-sd-input--narrow"
            min={1}
            max={100000}
            value={iterations}
            onChange={(e) => setIterations(Number(e.target.value))}
          />
        </label>
        <label className="gh-sd-inline">
          {t("thRounds")}
          <input
            type="number"
            className="gh-sd-input gh-sd-input--narrow"
            min={1}
            max={10000}
            value={rounds}
            onChange={(e) => setRounds(Number(e.target.value))}
          />
        </label>
        {running ? <Spinner label={t("analyzing")} /> : null}
      </div>
      {!report && !running ? <p className="gh-sd-note">{t("thIntro")}</p> : null}
      {report ? <Report report={report} t={t} onRun={run} /> : null}
    </div>
  );
}

function Section(props: { title: string; children: React.ReactNode; name: string }) {
  return (
    <section className="gh-sd-theory__card" aria-label={props.title} data-analysis={props.name}>
      <h3 className="gh-sd-subtitle">{props.title}</h3>
      {props.children}
    </section>
  );
}

function Report(props: { report: TheoryReport; t: T; onRun: (key: string) => void }) {
  const { report: r, t } = props;
  const { locale } = useLocale();
  const nf = r.normal_form;
  return (
    <div className="gh-sd-theory__grid">
      {r.feasibility ? (
        <Section name="feasibility" title={t("thFeasibility")}>
          <div className="gh-sd-row">
            {r.feasibility.labels.map((label) => (
              <Badge key={label} tone="accent">
                {label}
              </Badge>
            ))}
          </div>
          <p>
            {t("thTree", { n: r.feasibility.tree_log10.toFixed(1) })} ·{" "}
            {t("thLeaves", { n: r.feasibility.leaves_log10.toFixed(1) })} ·{" "}
            {t("thBranching", { n: r.feasibility.branching.toFixed(1) })} ·{" "}
            {t("thDepth", {
              n: r.feasibility.depth.mean.toFixed(1),
              m: r.feasibility.depth.max,
            })}{" "}
            <span className="gh-sd-muted">({t("thSamples", { n: r.feasibility.samples })})</span>
          </p>
          {Object.keys(r.feasibility.exact).length ? (
            <p>
              <span className="gh-sd-muted">{t("thExact")}: </span>
              {exactText(r.feasibility.exact, t, locale)}
            </p>
          ) : null}
          <p className="gh-sd-muted">{t("thRecommended")}:</p>
          <ul className="gh-sd-theory__list">
            {r.feasibility.recommendations.map((rec) => (
              <li key={rec.code}>
                {rec.text}{" "}
                {rec.phase ? (
                  <Badge tone="warning">{t("thPhase", { p: rec.phase })}</Badge>
                ) : RECOMMENDATION_ACTION[rec.code] ? (
                  <Button
                    size="sm"
                    onClick={() => props.onRun(RECOMMENDATION_ACTION[rec.code] ?? "")}
                  >
                    {t("thRun")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {r.solve || r.count ? (
        <Section name="solve" title={t("thSolve")}>
          {r.count ? (
            <p>
              {t("thPositions", { n: r.count.positions.toLocaleString(locale) })} ·{" "}
              {t("thTerminals", { n: r.count.terminals.toLocaleString(locale) })}
              {r.count.games !== null
                ? ` · ${t("thGames", { n: r.count.games.toLocaleString(locale) })}`
                : ""}
            </p>
          ) : null}
          {r.solve ? (
            <>
              <p>
                <strong>
                  {t("thValue")}: ({r.solve.value.join(", ")})
                </strong>{" "}
                <span className="gh-sd-muted">
                  ·{" "}
                  {r.solve.method === "alphabeta" ? t("thMethodAlphabeta") : t("thMethodBackward")}{" "}
                  · {t("thStates", { n: r.solve.states.toLocaleString(locale) })}
                </span>
              </p>
              {r.solve.best.length ? (
                <p>
                  {t("thBest")}: <code>{r.solve.best.join(" · ")}</code>
                </p>
              ) : null}
              <p>
                {t("thPv")}: <code>{r.solve.pv.join(" → ")}</code>
              </p>
            </>
          ) : null}
        </Section>
      ) : null}

      {nf ? (
        <Section name="normal_form" title={t("thNormalForm")}>
          <Matrix report={r} t={t} />
        </Section>
      ) : null}

      {r.nash ? (
        <Section name="nash" title={t("thEquilibria")}>
          <p>
            {t("thPure")}:{" "}
            {r.nash.pure.length
              ? r.nash.pure.map((p) => profileName(r.nash?.strategies ?? [], p)).join(", ")
              : t("thNone")}
          </p>
          {r.nash.mixed?.length ? (
            <>
              <p>
                {t("thMixed")}{" "}
                {r.nash.complete === false ? (
                  <span className="gh-sd-muted">{t("thIncomplete")}</span>
                ) : null}
              </p>
              <ol className="gh-sd-theory__list">
                {r.nash.mixed.map((eq) => (
                  <li key={JSON.stringify(eq.strategies)}>
                    {eq.strategies
                      .map((mix, k) =>
                        mix
                          .map((q, s) => [q, s] as const)
                          .filter(([q]) => value(q) !== 0)
                          .map(([q, s]) => `${r.nash?.strategies[k]?.[s] ?? s}=${fmt(q)}`)
                          .join(", "),
                      )
                      .join(" | ")}{" "}
                    <span className="gh-sd-muted">→ ({eq.payoffs.map(fmt).join(", ")})</span>
                  </li>
                ))}
              </ol>
            </>
          ) : null}
          {r.nash.zero_sum ? (
            <p>
              <strong>
                {t("thZeroSum")}: {fmt(r.nash.zero_sum.value)}
              </strong>
            </p>
          ) : null}
        </Section>
      ) : null}

      {r.dominance ? (
        <Section name="dominance" title={t("thDominance")}>
          {(["strict", "weak"] as const).map((kind) => {
            const steps = r.dominance?.[kind].steps ?? [];
            return (
              <p key={kind}>
                {t(kind === "strict" ? "thStrict" : "thWeak")}:{" "}
                {steps.length
                  ? steps
                      .map(([p, s]) => `${r.dominance?.strategies[p]?.[s] ?? s} (${p + 1})`)
                      .join(" → ")
                  : t("thNothing")}
              </p>
            );
          })}
        </Section>
      ) : null}

      {r.correlated ? (
        <Section name="correlated" title={t("thCorrelated")}>
          <p>
            {r.correlated.distribution
              .map(
                (d) =>
                  `${profileName(r.correlated?.strategies ?? [], d.profile)}: ${fmt(d.probability)}`,
              )
              .join(" · ")}{" "}
            <span className="gh-sd-muted">
              · {t("thWelfare", { n: fmt(r.correlated.welfare) })}
            </span>
          </p>
        </Section>
      ) : null}

      {r.pareto ? (
        <Section name="pareto" title={t("thEfficiency")}>
          <p>
            {t("thPareto")}:{" "}
            {r.pareto.optimal.map((p) => profileName(r.pareto?.strategies ?? [], p)).join(", ")}
          </p>
          {r.pareto.equilibria_dominated.map((item) => (
            <p key={item.profile.join(",")}>
              {t("thDominatedEq", {
                eq: profileName(r.pareto?.strategies ?? [], item.profile),
                by: item.by.map((q) => profileName(r.pareto?.strategies ?? [], q)).join(", "),
              })}
            </p>
          ))}
          <p>
            {t("thUtilitarian")}: {fmt(r.pareto.utilitarian.value)}
            {r.pareto.price_of_anarchy !== null ? (
              <>
                {" "}
                · {t("thPoa")}: {fmt(r.pareto.price_of_anarchy)} · {t("thPos")}:{" "}
                {fmt(r.pareto.price_of_stability)}
              </>
            ) : null}
          </p>
        </Section>
      ) : null}

      {r.sequence_form ? (
        <Section name="sequence_form" title={t("thSequence")}>
          <p>
            <strong>
              {t("thSeatValue")}: {fmt(r.sequence_form.value)}
            </strong>{" "}
            · {t("thExploitability")}: {fmt(r.sequence_form.exploitability)}
          </p>
          <PolicyTable rows={r.sequence_form.policy} t={t} />
        </Section>
      ) : null}

      {r.cfr ? (
        <Section name="cfr" title={`${r.cfr.plus ? "CFR+" : "CFR"} · ${r.cfr.iterations}`}>
          <p>
            <strong>
              {t("thValue")}: ({r.cfr.values.map(fmt).join(", ")})
            </strong>{" "}
            · {t("thExploitability")}: {fmt(r.cfr.exploitability)}
          </p>
          <ConvergenceChart points={r.cfr.convergence} t={t} />
          <PolicyTable rows={r.cfr.policy} t={t} />
        </Section>
      ) : null}

      {r.grundy ? (
        <Section name="grundy" title={t("thGrundy")}>
          <p>
            <strong>{t("thGrundyValue", { n: r.grundy.value, c: r.grundy.outcome })}</strong> (
            {t(r.grundy.outcome === "N" ? "thMover" : "thPrevious")})
          </p>
          {r.grundy.winning.length ? (
            <p>
              {t("thWinning")}: <code>{r.grundy.winning.join(" · ")}</code>
            </p>
          ) : null}
          <table className="gh-sd-stats">
            <tbody>
              {r.grundy.moves.map((m) => (
                <tr key={m.move} className={cx(m.grundy === 0 && "is-highlight")}>
                  <th>{m.move}</th>
                  <td>{m.grundy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {r.coop ? (
        <Section name="coop" title={t("thCoop")}>
          <table className="gh-sd-stats">
            <caption className="gh-sd-muted">{t("thCoalitions")}</caption>
            <tbody>
              {r.coop.values
                .filter((v) => v.coalition.length)
                .map((v) => (
                  <tr key={v.coalition.join(",")}>
                    <th>{`v({${v.coalition.map((i) => i + 1).join(", ")}})`}</th>
                    <td>{fmt(v.value)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
          <p>
            {t("thShapley")}: ({r.coop.shapley.map(fmt).join(", ")}) · {t("thBanzhaf")}: (
            {r.coop.banzhaf.map(fmt).join(", ")})
          </p>
          <p>
            {t("thCore")}: {r.coop.core ? `(${r.coop.core.map(fmt).join(", ")})` : t("thEmpty")}
            {r.coop.nucleolus ? (
              <>
                {" "}
                · {t("thNucleolus")}: ({r.coop.nucleolus.map(fmt).join(", ")})
              </>
            ) : null}
          </p>
          {r.coop.nash_bargaining ? (
            <p>
              {t("thBargaining")}: ({r.coop.nash_bargaining.payoffs.map(fmt).join(", ")}){" "}
              <span className="gh-sd-muted">
                {t("thFrom", { d: `(${r.coop.nash_bargaining.disagreement.map(fmt).join(", ")})` })}
              </span>
            </p>
          ) : null}
        </Section>
      ) : null}

      {r.tournament ? (
        <Section name="tournament" title={t("thTournament")}>
          <table className="gh-sd-stats">
            <caption className="gh-sd-muted">{t("thRanking")}</caption>
            <thead>
              <tr>
                <th>#</th>
                <th>{t("thStrategy")}</th>
                <th>{t("thScore")}</th>
              </tr>
            </thead>
            <tbody>
              {r.tournament.ranking.map((item, k) => (
                <tr key={item.name}>
                  <td>{k + 1}</td>
                  <th>{item.name}</th>
                  <td>{item.score.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <EcologicalChart
            names={r.tournament.names}
            series={r.tournament.ecological.series}
            generations={r.tournament.ecological.generations}
            t={t}
          />
        </Section>
      ) : null}

      {Object.entries(r.errors).length ? (
        <ul className="gh-sd-problem-list">
          {Object.entries(r.errors).map(([name, message]) => (
            <li key={name} className="gh-sd-problem is-warning">
              <span className="gh-sd-problem__code">{name}</span> {message}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function exactText(exact: Record<string, number>, t: T, locale: string): string {
  const parts: string[] = [];
  const key: Record<string, MessageKey> = {
    positions: "thPositions",
    nodes: "thNodes",
    terminals: "thTerminals",
    games: "thGames",
    infosets: "thInfosets",
  };
  for (const [name, n] of Object.entries(exact)) {
    const k = key[name];
    if (k) parts.push(t(k, { n: n.toLocaleString(locale) }));
  }
  return parts.join(" · ");
}

// --- La matriz de pagos --------------------------------------------------------------------------

function Matrix(props: { report: TheoryReport; t: T }) {
  const nf = props.report.normal_form;
  const t = props.t;
  if (!nf) return null;
  const [rows = [], cols = []] = nf.strategies;
  if (nf.strategies.length !== 2 || rows.length * cols.length > 100) {
    return (
      <>
        <p>{t("thTooBig", { m: rows.length, n: cols.length })}</p>
        <dl className="gh-sd-theory__legend">
          {Object.entries(nf.infosets).map(([id, description]) => (
            <div key={id}>
              <dt>I{id}</dt>
              <dd>{description || "—"}</dd>
            </div>
          ))}
        </dl>
      </>
    );
  }
  const cell = new Map(nf.payoffs.map((p) => [p.profile.join(","), p.payoffs]));
  const pay = (i: number, j: number, k: number) => value(cell.get(`${i},${j}`)?.[k] ?? "0");
  const bestRow = (i: number, j: number) =>
    rows.every((_, other) => pay(other, j, 0) <= pay(i, j, 0));
  const bestCol = (i: number, j: number) =>
    cols.every((_, other) => pay(i, other, 1) <= pay(i, j, 1));
  return (
    <>
      <table className="gh-sd-matrix">
        <thead>
          <tr>
            <th />
            {cols.map((c) => (
              <th key={c} scope="col">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((rname, i) => (
            <tr key={rname}>
              <th scope="row">{rname}</th>
              {cols.map((cname, j) => {
                const u = cell.get(`${i},${j}`) ?? [];
                const a = bestRow(i, j);
                const b = bestCol(i, j);
                return (
                  <td
                    key={cname}
                    className={cx(a && b && "is-equilibrium")}
                    data-testid={`cell-${i}-${j}`}
                  >
                    {a ? <u>{u[0]}</u> : u[0]}, {b ? <u>{u[1]}</u> : u[1]}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="gh-sd-note">{t("thMatrixLegend")}</p>
    </>
  );
}

// --- La estrategia por conjunto de información ---------------------------------------------------

function PolicyTable(props: { rows: PolicyRow[]; t: T }) {
  const [all, setAll] = useState(false);
  const shown = all ? props.rows : props.rows.slice(0, 24);
  return (
    <details className="gh-sd-theory__policy" open={props.rows.length <= 12}>
      <summary>
        {props.t("thPolicy")} ({props.rows.length})
      </summary>
      <table className="gh-sd-stats">
        <tbody>
          {shown.map((row) => (
            <tr key={row.infoset}>
              <td>{row.player + 1}</td>
              <th className="gh-sd-theory__infoset">{row.description || `I${row.infoset}`}</th>
              <td className="gh-sd-theory__probs">
                {row.actions.map((a, k) => {
                  const q = row.probs[k] ?? 0;
                  return (
                    <span key={a} className="gh-sd-theory__prob">
                      <span className="gh-sd-theory__track">
                        <span
                          className="gh-sd-theory__bar"
                          style={{ width: `${Math.round(value(q) * 100)}%` }}
                        />
                      </span>
                      {a}={fmt(q)}
                    </span>
                  );
                })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {props.rows.length > shown.length ? (
        <Button size="sm" onClick={() => setAll(true)}>
          +{props.rows.length - shown.length}
        </Button>
      ) : null}
    </details>
  );
}

// --- Gráficas ------------------------------------------------------------------------------------

const W = 420;
const H = 180;
const PAD = { left: 44, right: 64, top: 10, bottom: 26 };

/** Explotabilidad frente a iteraciones (log-log), con cruz y tooltip al pasar el ratón. */
function ConvergenceChart(props: { points: [number, TheoryNumber][]; t: T }) {
  const [hover, setHover] = useState<number | null>(null);
  const data = props.points
    .map(([i, e]) => [i, value(e)] as const)
    .filter(([i, e]) => i > 0 && e > 0);
  if (data.length < 2) return null;
  const xs = data.map(([i]) => Math.log10(i));
  const ys = data.map(([, e]) => Math.log10(e));
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const y0 = Math.floor(Math.min(...ys));
  const y1 = Math.max(Math.ceil(Math.max(...ys)), y0 + 1);
  const px = (x: number) => PAD.left + ((x - x0) / (x1 - x0 || 1)) * (W - PAD.left - PAD.right);
  const py = (y: number) => PAD.top + ((y1 - y) / (y1 - y0)) * (H - PAD.top - PAD.bottom);
  const path = xs.map((x, k) => `${k ? "L" : "M"}${px(x).toFixed(1)},${py(ys[k] ?? 0).toFixed(1)}`);
  const ticks = Array.from({ length: y1 - y0 + 1 }, (_, k) => y0 + k);
  const last = data[data.length - 1];
  const at = hover === null ? null : data[hover];
  return (
    <figure className="gh-sd-chart">
      <figcaption className="gh-sd-muted">
        {props.t("thConvergence")}: {props.t("thExploitability").toLowerCase()} /{" "}
        {props.t("thIterations").toLowerCase()}
      </figcaption>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={props.t("thConvergence")}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const x = ((e.clientX - box.left) / box.width) * W;
          let best = 0;
          xs.forEach((v, k) => {
            if (Math.abs(px(v) - x) < Math.abs(px(xs[best] ?? 0) - x)) best = k;
          });
          setHover(best);
        }}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((tk) => (
          <g key={tk}>
            <line
              className="gh-sd-chart__grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={py(tk)}
              y2={py(tk)}
            />
            <text className="gh-sd-chart__axis" x={PAD.left - 6} y={py(tk) + 4} textAnchor="end">
              1e{tk}
            </text>
          </g>
        ))}
        <text className="gh-sd-chart__axis" x={PAD.left} y={H - 6}>
          {data[0]?.[0]}
        </text>
        <text className="gh-sd-chart__axis" x={W - PAD.right} y={H - 6} textAnchor="end">
          {last?.[0]}
        </text>
        <path className="gh-sd-chart__line is-series-1" d={path.join(" ")} />
        {last ? (
          <text
            className="gh-sd-chart__label"
            x={px(xs[xs.length - 1] ?? 0) + 6}
            y={py(ys[ys.length - 1] ?? 0) + 4}
          >
            {fmt(last[1])}
          </text>
        ) : null}
        {at && hover !== null ? (
          <g>
            <line
              className="gh-sd-chart__cross"
              x1={px(xs[hover] ?? 0)}
              x2={px(xs[hover] ?? 0)}
              y1={PAD.top}
              y2={H - PAD.bottom}
            />
            <circle
              className="gh-sd-chart__dot is-series-1"
              cx={px(xs[hover] ?? 0)}
              cy={py(ys[hover] ?? 0)}
              r={4}
            />
            <text className="gh-sd-chart__tip" x={W - PAD.right} y={PAD.top + 10} textAnchor="end">
              {at[0]}: {fmt(at[1])}
            </text>
          </g>
        ) : null}
      </svg>
      <ChartTable
        head={[props.t("thIterations"), props.t("thExploitability")]}
        rows={data.map(([i, e]) => [String(i), fmt(e)])}
      />
    </figure>
  );
}

/** La proporción de las estrategias en la simulación ecológica: las cuatro que acaban con más
 * población, cada una con su color, y el resto juntas en «otras». */
function EcologicalChart(props: {
  names: string[];
  series: number[][];
  generations: number;
  t: T;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const final = props.series[props.series.length - 1] ?? [];
  const order = props.names.map((_, k) => k).sort((a, b) => (final[b] ?? 0) - (final[a] ?? 0));
  const top = order.slice(0, 4);
  const rest = order.slice(4);
  const lines = [
    ...top.map((k, slot) => ({
      name: props.names[k] ?? "",
      cls: `is-series-${slot + 1}`,
      ys: props.series.map((row) => row[k] ?? 0),
    })),
    ...(rest.length
      ? [
          {
            name: props.t("thOthers"),
            cls: "is-series-other",
            ys: props.series.map((row) => rest.reduce((sum, k) => sum + (row[k] ?? 0), 0)),
          },
        ]
      : []),
  ];
  const n = props.series.length;
  const px = (k: number) => PAD.left + (k / Math.max(n - 1, 1)) * (W - PAD.left - PAD.right);
  const py = (y: number) => PAD.top + (1 - y) * (H - PAD.top - PAD.bottom);
  const step = props.generations / Math.max(n - 1, 1);
  return (
    <figure className="gh-sd-chart">
      <figcaption className="gh-sd-muted">
        {props.t("thEcological", { n: props.generations })}
      </figcaption>
      <ul className="gh-sd-chart__legend">
        {lines.map((l) => (
          <li key={l.name}>
            <span className={cx("gh-sd-chart__key", l.cls)} />
            {l.name}
          </li>
        ))}
      </ul>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={props.t("thEcological", { n: props.generations })}
        onMouseMove={(e) => {
          const box = e.currentTarget.getBoundingClientRect();
          const x = ((e.clientX - box.left) / box.width) * W;
          const k = Math.round(((x - PAD.left) / (W - PAD.left - PAD.right)) * (n - 1));
          setHover(Math.min(n - 1, Math.max(0, k)));
        }}
        onMouseLeave={() => setHover(null)}
      >
        {[0, 0.5, 1].map((y) => (
          <g key={y}>
            <line
              className="gh-sd-chart__grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={py(y)}
              y2={py(y)}
            />
            <text className="gh-sd-chart__axis" x={PAD.left - 6} y={py(y) + 4} textAnchor="end">
              {Math.round(y * 100)} %
            </text>
          </g>
        ))}
        {lines.map((l) => (
          <path
            key={l.name}
            className={cx("gh-sd-chart__line", l.cls)}
            d={l.ys
              .map((y, k) => `${k ? "L" : "M"}${px(k).toFixed(1)},${py(y).toFixed(1)}`)
              .join(" ")}
          />
        ))}
        {endLabels(lines.map((l) => py(l.ys[l.ys.length - 1] ?? 0))).map((k) => {
          const l = lines[k];
          if (!l) return null;
          return (
            <text
              key={`label-${l.name}`}
              className="gh-sd-chart__label"
              x={W - PAD.right + 6}
              y={py(l.ys[l.ys.length - 1] ?? 0) + 4}
            >
              {l.name} {Math.round((l.ys[l.ys.length - 1] ?? 0) * 100)} %
            </text>
          );
        })}
        {hover !== null ? (
          <g>
            <line
              className="gh-sd-chart__cross"
              x1={px(hover)}
              x2={px(hover)}
              y1={PAD.top}
              y2={H - PAD.bottom}
            />
            <text className="gh-sd-chart__tip" x={PAD.left + 4} y={PAD.top + 10}>
              {Math.round(hover * step)}:{" "}
              {lines.map((l) => `${l.name} ${Math.round((l.ys[hover] ?? 0) * 100)} %`).join(" · ")}
            </text>
          </g>
        ) : null}
      </svg>
      <ChartTable
        head={["#", ...lines.map((l) => l.name)]}
        rows={props.series.map((_, k) => [
          String(Math.round(k * step)),
          ...lines.map((l) => `${Math.round((l.ys[k] ?? 0) * 1000) / 10} %`),
        ])}
      />
    </figure>
  );
}

/** Las líneas cuya etiqueta final cabe sin pisar otra (separadas al menos 11 px): cuando las
 * líneas convergen, las identifican la leyenda y el tooltip. */
export function endLabels(ys: number[]): number[] {
  const order = ys.map((y, k) => [y, k] as const).sort((a, b) => a[0] - b[0]);
  const keep: number[] = [];
  order.forEach(([y, k], i) => {
    const prev = order[i - 1];
    const next = order[i + 1];
    if ((!prev || y - prev[0] >= 11) && (!next || next[0] - y >= 11)) keep.push(k);
  });
  return keep.sort((a, b) => a - b);
}

/** Los datos de una gráfica como tabla (para leerlos con precisión o sin ver el color). */
function ChartTable(props: { head: string[]; rows: string[][] }) {
  return (
    <details className="gh-sd-chart__data">
      <summary>⋯</summary>
      <table className="gh-sd-stats">
        <thead>
          <tr>
            {props.head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {props.rows.map((row) => (
            <tr key={row[0]}>
              {row.map((c, k) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: columnas fijas.
                <td key={k}>{c}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
