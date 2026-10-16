// SPDX-License-Identifier: Apache-2.0
/** Diálogos: juego nuevo desde una plantilla y el diseñador de componentes. */

import { pickText, useLocale, useMessages } from "@gamehub/i18n";
import { Button, cx } from "@gamehub/ui-kit";
import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import { useStudio } from "../context";
import { messages } from "../messages";
import { deckSource, diceSource, graphBoardSource, gridSource } from "./components";

export function Dialog(props: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal?.();
    return () => dialog?.close?.();
  }, []);
  return (
    <dialog
      ref={ref}
      className={cx("gh-sd-dialog", props.wide && "is-wide")}
      onCancel={(e) => {
        e.preventDefault();
        props.onClose();
      }}
      aria-label={props.title}
    >
      <header>
        <h2>{props.title}</h2>
        <button type="button" className="gh-sd-icon" aria-label="cerrar" onClick={props.onClose}>
          ✕
        </button>
      </header>
      {props.children}
    </dialog>
  );
}

export function NewGameDialog(props: { onClose: () => void }) {
  const t = useMessages(messages);
  const { locale } = useLocale();
  const [state, studio] = useStudio();
  const templates = state.workspace?.templates ?? [];
  const [name, setName] = useState("");
  const [title, setTitle] = useState("");
  const [template, setTemplate] = useState(templates[0]?.id ?? "vacio");
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  const slug = (text: string) =>
    text
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  return (
    <Dialog title={t("newGameTitle")} onClose={props.onClose}>
      <form
        className="gh-sd-dialog__body"
        onSubmit={async (e) => {
          e.preventDefault();
          try {
            await studio.newGame(name || slug(title), template, title || undefined);
            props.onClose();
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <label htmlFor={`${id}-title`}>{t("title")}</label>
        <input
          id={`${id}-title`}
          className="gh-sd-input"
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            if (!name || name === slug(title)) setName(slug(e.target.value));
          }}
        />
        <label htmlFor={`${id}-name`}>{t("name")}</label>
        <input
          id={`${id}-name`}
          className="gh-sd-input is-mono"
          value={name}
          pattern="[a-z][a-z0-9]*(-[a-z0-9]+)*"
          onChange={(e) => setName(e.target.value)}
        />
        <p className="gh-sd-field__hint">{t("nameHint")}</p>
        <fieldset className="gh-sd-templates">
          <legend>{t("template")}</legend>
          {templates.map((tpl) => (
            <label
              key={tpl.id}
              className={cx("gh-sd-template", template === tpl.id && "is-selected")}
            >
              <input
                type="radio"
                name="template"
                value={tpl.id}
                checked={template === tpl.id}
                onChange={() => setTemplate(tpl.id)}
              />
              <strong>{pickText(tpl.title, locale)}</strong>
              <span>{pickText(tpl.description, locale)}</span>
            </label>
          ))}
        </fieldset>
        {error ? <p className="gh-sd-field__error">{error}</p> : null}
        <footer>
          <Button onClick={props.onClose}>{t("cancel")}</Button>
          <Button type="submit" variant="primary" disabled={!name && !title}>
            {t("create")}
          </Button>
        </footer>
      </form>
    </Dialog>
  );
}

export function DesignerDialog(props: { onClose: () => void }) {
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const [tab, setTab] = useState<"deck" | "board" | "dice">("deck");
  const [error, setError] = useState<string | null>(null);
  const insert = async (source: {
    items: string;
    imports?: { path: string[]; names: string[] };
  }) => {
    try {
      setError(null);
      const ops = [];
      if (source.imports)
        ops.push({ op: "addImport", path: source.imports.path, names: source.imports.names });
      ops.push({ op: "insertSource", source: source.items });
      await studio.apply(ops);
      props.onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return (
    <Dialog title={t("designer")} onClose={props.onClose} wide>
      <div className="gh-sd-tabs" role="tablist">
        {(["deck", "board", "dice"] as const).map((k) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={tab === k}
            className={tab === k ? "is-active" : ""}
            onClick={() => setTab(k)}
          >
            {t(k)}
          </button>
        ))}
      </div>
      <div className="gh-sd-dialog__body">
        {tab === "deck" ? <DeckDesigner onInsert={insert} /> : null}
        {tab === "board" ? <BoardDesigner onInsert={insert} /> : null}
        {tab === "dice" ? <DiceDesigner onInsert={insert} /> : null}
        {error ? <p className="gh-sd-field__error">{error}</p> : null}
      </div>
    </Dialog>
  );
}

type Insert = (source: { items: string; imports?: { path: string[]; names: string[] } }) => void;

function Preview(props: { text: string }) {
  return <pre className="gh-sd-preview">{props.text}</pre>;
}

function DeckDesigner(props: { onInsert: Insert }) {
  const t = useMessages(messages);
  const [french, setFrench] = useState(false);
  const [suits, setSuits] = useState("Oros, Copas, Espadas, Bastos");
  const [ranks, setRanks] = useState(
    "Uno, Dos, Tres, Cuatro, Cinco, Seis, Siete, Sota, Caballo, Rey",
  );
  const [card, setCard] = useState("Card");
  const source = deckSource({ french, suits, ranks, card });
  return (
    <div className="gh-sd-designer">
      <label className="gh-sd-inline">
        <input type="checkbox" checked={french} onChange={(e) => setFrench(e.target.checked)} />
        {t("useFrench")}
      </label>
      {!french ? (
        <>
          <label>
            {t("deckName")}
            <input
              className="gh-sd-input is-mono"
              value={card}
              onChange={(e) => setCard(e.target.value)}
            />
          </label>
          <label>
            {t("suits")}
            <input
              className="gh-sd-input is-mono"
              value={suits}
              onChange={(e) => setSuits(e.target.value)}
            />
          </label>
          <label>
            {t("ranks")}
            <input
              className="gh-sd-input is-mono"
              value={ranks}
              onChange={(e) => setRanks(e.target.value)}
            />
          </label>
        </>
      ) : null}
      <Preview text={source.items} />
      <Button variant="primary" onClick={() => props.onInsert(source)}>
        {t("insert")}
      </Button>
    </div>
  );
}

function BoardDesigner(props: { onInsert: Insert }) {
  const t = useMessages(messages);
  const [kind, setKind] = useState<"grid" | "graph">("grid");
  const [width, setWidth] = useState(3);
  const [height, setHeight] = useState(3);
  const [cell, setCell] = useState("Mark?");
  const [squares, setSquares] = useState("A, B, C, D");
  const [edges, setEdges] = useState("A-B, B-C, C-D, D-A");
  const source =
    kind === "grid" ? gridSource({ width, height, cell }) : graphBoardSource({ squares, edges });
  return (
    <div className="gh-sd-designer">
      <div className="gh-sd-row">
        <label className="gh-sd-inline">
          <input type="radio" checked={kind === "grid"} onChange={() => setKind("grid")} />
          {t("gridBoard")}
        </label>
        <label className="gh-sd-inline">
          <input type="radio" checked={kind === "graph"} onChange={() => setKind("graph")} />
          {t("graphBoard")}
        </label>
      </div>
      {kind === "grid" ? (
        <div className="gh-sd-row">
          <label>
            {t("width")}
            <input
              type="number"
              min={1}
              max={30}
              className="gh-sd-input"
              value={width}
              onChange={(e) => setWidth(Number(e.target.value))}
            />
          </label>
          <label>
            {t("height")}
            <input
              type="number"
              min={1}
              max={30}
              className="gh-sd-input"
              value={height}
              onChange={(e) => setHeight(Number(e.target.value))}
            />
          </label>
          <label>
            {t("cellType")}
            <input
              className="gh-sd-input is-mono"
              value={cell}
              onChange={(e) => setCell(e.target.value)}
            />
          </label>
        </div>
      ) : (
        <>
          <label>
            {t("squares")}
            <input
              className="gh-sd-input is-mono"
              value={squares}
              onChange={(e) => setSquares(e.target.value)}
            />
          </label>
          <label>
            {t("edges")}
            <input
              className="gh-sd-input is-mono"
              value={edges}
              onChange={(e) => setEdges(e.target.value)}
            />
          </label>
        </>
      )}
      <Preview text={source.items} />
      <Button variant="primary" onClick={() => props.onInsert(source)}>
        {t("insert")}
      </Button>
    </div>
  );
}

function DiceDesigner(props: { onInsert: Insert }) {
  const t = useMessages(messages);
  const [, studio] = useStudio();
  const nodes = (studio.game?.flow.nodes ?? []).filter((n) => n.kind !== "phase").map((n) => n.id);
  const [count, setCount] = useState(2);
  const [faces, setFaces] = useState(6);
  const [next, setNext] = useState(studio.game?.flow.start?.target ?? nodes[0] ?? "");
  const source = diceSource({ count, faces, next });
  return (
    <div className="gh-sd-designer">
      <div className="gh-sd-row">
        <label>
          {t("diceCount")}
          <input
            type="number"
            min={1}
            max={20}
            className="gh-sd-input"
            value={count}
            onChange={(e) => setCount(Number(e.target.value))}
          />
        </label>
        <label>
          {t("faces")}
          <input
            type="number"
            min={2}
            max={100}
            className="gh-sd-input"
            value={faces}
            onChange={(e) => setFaces(Number(e.target.value))}
          />
        </label>
        <label>
          {t("thenGoTo")}
          <select className="gh-sd-input" value={next} onChange={(e) => setNext(e.target.value)}>
            {nodes.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
            <option value="">RollDice</option>
          </select>
        </label>
      </div>
      <Preview text={source.items} />
      <Button variant="primary" onClick={() => props.onInsert(source)}>
        {t("insert")}
      </Button>
    </div>
  );
}
