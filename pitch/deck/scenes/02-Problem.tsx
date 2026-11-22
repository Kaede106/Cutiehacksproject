import { Reveal, Scene, useScene } from 'beatdeck';
import { Eyebrow } from '../ui';

const WEEK: [string, string, string][] = [
  ['ripe?', 'Ripeness, judged tree by tree.', 'Is this one ready, or next week?'],
  ['sick?', 'Disease, caught late.', 'You only see a tree when you walk past it.'],
  ['water?', 'Watering, on a fixed schedule.', 'Whatever the soil and the weather are doing.'],
];

const QUESTIONS = ['Is it ready to pick?', 'Is it sick?', 'Does it need water?'];

function Problem_() {
  const { here, b } = useScene();
  const at = (k: number) => here && b === k;
  const past = (k: number) => here && b > k;
  return (
    <>
      {/* 02.1 Minecraft */}
      <Eyebrow on={at(0)} out={past(0)} y={170}>What inspired us</Eyebrow>
      <Reveal on={at(0)} out={past(0)} x={150} y={250} delay={100}>
        <div className="t-statement" style={{ fontSize: 190 }}>Minecraft has<br />automatic farms.</div>
      </Reveal>
      <Reveal on={at(0)} out={past(0)} x={160} y={680} delay={400}>
        <div className="cf-sub">Build it once. It grows and harvests itself.</div>
      </Reveal>

      {/* 02.2 real groves don't */}
      <Reveal on={at(1)} out={past(1)} x={150} y={220}>
        <div className="t-statement" style={{ fontSize: 170 }}>Real orange groves<br /><span style={{ color: 'var(--accent)' }}>don’t.</span></div>
      </Reveal>
      <Reveal on={at(1)} out={past(1)} x={160} y={860} delay={500}>
        <div className="t-meta" style={{ fontSize: 24 }}>Riverside · where California’s navel orange industry began</div>
      </Reveal>

      {/* 02.3 a grower's week: walk the rows */}
      <Eyebrow on={here && b >= 2 && b <= 5} out={past(5)}>A grower’s week</Eyebrow>
      <Reveal on={at(2)} out={past(2)} x={150} y={300}>
        <div className="t-statement" style={{ fontSize: 190 }}>Walk the rows.<br /><span style={{ color: 'var(--accent)' }}>One tree at a time.</span></div>
      </Reveal>

      {/* 02.4–02.6 ripeness, disease, watering: one per beat, earlier ones dim */}
      {WEEK.map(([k, head, sub], i) => {
        const on = here && b >= 3 + i && b <= 5;
        const current = at(3 + i);
        return (
          <Reveal key={k} on={on} out={past(5)} x={150} y={240 + i * 230}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 44 }}>
              <span className="t-meta" style={{ fontSize: 28, width: 130, color: current ? 'var(--accent)' : 'var(--ink-3)', transition: 'color 400ms' }}>{k}</span>
              <div>
                <div className="t-statement" style={{ fontSize: 104, lineHeight: 1, color: current ? 'var(--ink)' : 'var(--ink-3)', transition: 'color 400ms' }}>{head}</div>
                <div className="cf-sub" style={{ fontSize: 36, marginTop: 16, color: current ? 'var(--ink-2)' : 'var(--ink-3)', transition: 'color 400ms' }}>{sub}</div>
              </div>
            </div>
          </Reveal>
        );
      })}

      {/* 02.7 the three questions, every tree, every week */}
      <Eyebrow on={at(6)}>Every tree, every week, by hand</Eyebrow>
      {QUESTIONS.map((q, i) => (
        <Reveal key={q} on={at(6)} x={150} y={240 + i * 220} delay={150 + i * 180}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 48 }}>
            <span className="t-meta" style={{ fontSize: 32, width: 70, color: 'var(--accent)' }}>0{i + 1}</span>
            <span className="t-statement" style={{ fontSize: 150 }}>{q}</span>
          </div>
        </Reveal>
      ))}
    </>
  );
}

/** 02 THE PROBLEM — Minecraft farms run themselves; a grower's week is three questions answered by hand. */
export const Problem = () => <Scene index={1}><Problem_ /></Scene>;
