// The agent's personality and its trade in the city (city/persona.ts): five quick questions (or a direct pick) for the
// personality, and one of four trades, each shown on the building of EdgeCraft-StrikeCity where it works. The preview
// says a line in the chosen voice. Nothing here changes how the agent trades.
import { useState } from "react";
import type { Look } from "../city/look";
import { JOBS, QUIZ, TEMPERS, TEMPER_COLOR, quizResult, type Job, type Moment, type Persona, type Temper } from "../city/persona";
import type { Dict, Lang } from "../i18n";
import { Sprite } from "./AvatarEditor";

const BASE = `${import.meta.env.BASE_URL ?? "/"}art/city/base.webp`;
const CITY_W = 96 * 16, CITY_H = 64 * 16;
// where each trade works, cut from the city's picture (art px: x, y, w, h)
const CROP: Record<Job, [number, number, number, number]> = {
  chartist: [56, 40, 240, 154], reporter: [56, 330, 272, 175], tape: [600, 380, 300, 192], guardian: [1200, 730, 230, 148],
};

export function placeArt(job: Job, w: number, h: number) {
  const [x, y, cw, ch] = CROP[job];
  const k = Math.max(w / cw, h / ch);
  return {
    width: w, height: h, backgroundImage: `url(${BASE})`, backgroundSize: `${CITY_W * k}px ${CITY_H * k}px`,
    backgroundPosition: `${-(x + cw / 2) * k + w / 2}px ${-(y + ch / 2) * k + h / 2}px`, imageRendering: "pixelated" as const,
  };
}

/** A line in this temper's voice ({mk}: a market, {r}: an R value). */
export function voiceLine(t: Dict, temper: Temper, moment: Moment, i = 0, mk = "BTC", r = "1,0"): string {
  const lines = t.persona.voice[temper]?.[moment] ?? [];
  return (lines[i % Math.max(1, lines.length)] ?? "").replace("{mk}", mk).replace("{r}", r);
}

export function PersonaPicker({ t, lang, value, onChange, look, idPrefix = "pp" }:
  { t: Dict; lang: Lang; value: Persona; onChange: (p: Persona) => void; look: Look | null; idPrefix?: string }) {
  const P = t.persona;
  const [mode, setMode] = useState<"quiz" | "pick">("quiz");
  const [answers, setAnswers] = useState<(number | null)[]>(() => QUIZ.map(() => null));
  const [q, setQ] = useState(0);
  const [line, setLine] = useState(0);
  const done = answers.every((a) => a != null);
  const r = lang === "es" ? "1,4" : "1.4";

  const answer = (qi: number, ai: number) => {
    const next = answers.map((a, i) => (i === qi ? ai : a));
    setAnswers(next);
    const res = quizResult(next);
    if (res) onChange({ ...value, temper: res });
    if (qi < QUIZ.length - 1) setQ(qi + 1);
  };
  const moments: Moment[] = ["win", "loss", "enter", "wait"];
  const say = voiceLine(t, value.temper, moments[line % moments.length], 0, "ETH", r);

  return (
    <div className="pp">
      <div className="pp-stage" style={{ ["--tc" as string]: TEMPER_COLOR[value.temper] }}>
        <div className="pp-place" style={placeArt(value.job, 220, 132)} aria-hidden="true" />
        <div className="pp-hero">
          <button type="button" className="pp-say" onClick={() => setLine((x) => x + 1)} aria-label={`${P.says}: ${say}`}>
            “{say}”
          </button>
          {look && <Sprite look={look} scale={5} anim="idle" play className="pp-sprite" />}
        </div>
        <p className="pp-who"><b>{P.tempers[value.temper].name}</b> · {P.jobs[value.job].name}</p>
        <p className="pp-where small faint">{P.worksAt(P.jobs[value.job].place)}</p>
      </div>

      <div className="pp-body">
        <section aria-labelledby={`${idPrefix}-temper`}>
          <h3 id={`${idPrefix}-temper`} className="pp-h">{P.temper}</h3>
          <div className="pp-tabs" role="tablist" aria-label={P.title}>
            {(["quiz", "pick"] as const).map((m) => (
              <button key={m} type="button" role="tab" id={`${idPrefix}-tab-${m}`} aria-selected={mode === m} aria-controls={`${idPrefix}-panel-${m}`}
                      onClick={() => setMode(m)}>{m === "quiz" ? P.quizTab : P.pickTab}</button>
            ))}
          </div>
          {mode === "quiz" ? (
            <div id={`${idPrefix}-panel-quiz`} role="tabpanel" aria-labelledby={`${idPrefix}-tab-quiz`} className="pp-quiz">
              <ol className="pp-steps" aria-label={P.quizLead}>
                {QUIZ.map((_, i) => (
                  <li key={i}><button type="button" aria-current={i === q ? "step" : undefined} className={answers[i] != null ? "on" : ""}
                                      onClick={() => setQ(i)} aria-label={`${i + 1} / ${QUIZ.length}`}>{i + 1}</button></li>
                ))}
              </ol>
              <fieldset className="pp-q">
                <legend>{P.questions[q].q}</legend>
                {P.questions[q].a.map((a, ai) => (
                  <label key={ai} className="pp-a">
                    <input type="radio" name={`${idPrefix}-q${q}`} checked={answers[q] === ai} onChange={() => answer(q, ai)} />
                    <span>{a}</span>
                  </label>
                ))}
              </fieldset>
              <p className="pp-result" role="status">
                {done ? <>{P.result(P.tempers[value.temper].name)}: <span className="muted">{P.tempers[value.temper].desc}</span></>
                  : <span className="faint">{P.answerAll}</span>}
              </p>
            </div>
          ) : (
            <div id={`${idPrefix}-panel-pick`} role="tabpanel" aria-labelledby={`${idPrefix}-tab-pick`}>
              <fieldset className="pp-cards">
                <legend className="sr-only">{P.title}</legend>
                {TEMPERS.map((tp) => (
                  <label key={tp} className="pp-card" style={{ ["--tc" as string]: TEMPER_COLOR[tp] }}>
                    <input type="radio" name={`${idPrefix}-temper`} checked={value.temper === tp} onChange={() => onChange({ ...value, temper: tp })} />
                    <span><b>{P.tempers[tp].name}</b><small>{P.tempers[tp].desc}</small>
                      <i className="pp-sample">“{voiceLine(t, tp, "loss", 0, "ETH", r)}”</i></span>
                  </label>
                ))}
              </fieldset>
            </div>
          )}
        </section>

        <section aria-labelledby={`${idPrefix}-job`}>
          <h3 id={`${idPrefix}-job`} className="pp-h">{P.jobTitle}</h3>
          <p className="small muted pp-sub">{P.jobSub}</p>
          <fieldset className="pp-jobs">
            <legend className="sr-only">{P.jobTitle}</legend>
            {JOBS.map((j) => (
              <label key={j} className="pp-job">
                <input type="radio" name={`${idPrefix}-job`} checked={value.job === j} onChange={() => onChange({ ...value, job: j })} />
                <span>
                  <span className="pp-job-art" style={placeArt(j, 96, 60)} aria-hidden="true" />
                  <span className="pp-job-txt"><b>{P.jobs[j].name}</b><small className="faint">{P.jobs[j].place}</small><small>{P.jobs[j].desc}</small></span>
                </span>
              </label>
            ))}
          </fieldset>
          <p className="small faint pp-never">{P.never}</p>
        </section>
      </div>
    </div>
  );
}
