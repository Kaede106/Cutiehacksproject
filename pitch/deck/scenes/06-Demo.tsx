import { Reveal, Scene, useScene } from 'beatdeck';

const CUES: [string, string][] = [
  ['Camera + control room', 'boxes, ripeness, ready counts, watering plan'],
  ['Telegram', 'summary, a question, a photo, /week'],
];

function Demo_() {
  const { here, b } = useScene();
  return (
    <>
      <Reveal on={here} x={160} y={170}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 22 }}>
          <span style={{ width: 22, height: 22, borderRadius: 11, background: 'var(--accent)' }} />
          <span className="t-eyebrow">Switch to the laptop</span>
        </div>
      </Reveal>
      <Reveal on={here} x={140} y={240} delay={120} ms={1100}>
        <div className="t-statement" style={{ fontSize: 300 }}>Live demo</div>
      </Reveal>
      {CUES.map(([head, sub], i) => {
        const current = here && b === i;
        return (
          <Reveal key={head} on={here && b >= i} x={150} y={600 + i * 190} delay={300}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 44 }}>
              <span className="t-meta" style={{ fontSize: 30, width: 64, color: current ? 'var(--accent)' : 'var(--ink-3)', transition: 'color 400ms' }}>0{i + 1}</span>
              <div>
                <div className="t-statement" style={{ fontSize: 92, lineHeight: 1, color: current ? 'var(--ink)' : 'var(--ink-3)', transition: 'color 400ms' }}>{head}</div>
                <div className="cf-note" style={{ fontSize: 26, marginTop: 14, color: current ? 'var(--ink-2)' : 'var(--ink-3)', transition: 'color 400ms' }}>{sub}</div>
              </div>
            </div>
          </Reveal>
        );
      })}
    </>
  );
}

/** 05 DEMO — two cues: camera window + dashboard, then Telegram. */
export const Demo = () => <Scene index={5}><Demo_ /></Scene>;
