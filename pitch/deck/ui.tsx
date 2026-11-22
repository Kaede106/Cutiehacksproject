import { Reveal } from 'beatdeck';

/** A small accent eyebrow at the top-left of the stage. */
export function Eyebrow({ on, out, children, y = 130 }: { on: boolean; out?: boolean; children: React.ReactNode; y?: number }) {
  return (
    <Reveal on={on} out={out} x={160} y={y}>
      <div className="t-eyebrow">{children}</div>
    </Reveal>
  );
}

/** A huge question that opens a section ("Is it ripe?"), with an optional line under it. */
export function BigQuestion({ on, out, eyebrow, text, sub, size = 250 }: { on: boolean; out?: boolean; eyebrow: string; text: string; sub?: string; size?: number }) {
  return (
    <>
      <Reveal on={on} out={out} x={160} y={300}><div className="t-eyebrow">{eyebrow}</div></Reveal>
      <Reveal on={on} out={out} x={146} y={370} delay={100} ms={1100}>
        <div className="t-statement" style={{ fontSize: size }}>{text}</div>
      </Reveal>
      {sub && (
        <Reveal on={on} out={out} x={160} y={680} delay={400}>
          <div className="cf-sub">{sub}</div>
        </Reveal>
      )}
    </>
  );
}

/** A chat bubble: the bot on the left (accent edge), the grower on the right. */
export function Bubble({ who, children, time }: { who: 'bot' | 'user'; children: React.ReactNode; time?: string }) {
  return (
    <div className={`cf-bubble ${who}`}>
      <div className="cf-bubble-text">{children}</div>
      {time && <div className="cf-bubble-time">{time}</div>}
    </div>
  );
}

/** A small, honest label under example content. */
export function ExampleNote({ on, out, y, x = 330, children }: { on: boolean; out?: boolean; y: number; x?: number; children: React.ReactNode }) {
  return (
    <Reveal on={on} out={out} x={x} y={y} delay={500}>
      <div className="cf-note">{children}</div>
    </Reveal>
  );
}

/**
 * Rows that arrive one per beat and stay; the newest is bright, earlier ones dim.
 * `first` = the beat (0-based, inside the scene) on which row 0 arrives.
 */
export function StackedRows({ here, b, first, rows, y = 230, step = 190, size = 84 }: {
  here: boolean; b: number; first: number; rows: [string, string?][]; y?: number; step?: number; size?: number;
}) {
  return (
    <>
      {rows.map(([head, sub], i) => {
        const on = here && b >= first + i;
        const current = here && b === first + i;
        return (
          <Reveal key={head} on={on} x={150} y={y + i * step}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 44 }}>
              <span className="t-meta" style={{ fontSize: 30, width: 64, color: current ? 'var(--accent)' : 'var(--ink-3)', transition: 'color 400ms' }}>0{i + 1}</span>
              <div>
                <div className="t-statement" style={{ fontSize: size, lineHeight: 1, color: current ? 'var(--ink)' : 'var(--ink-3)', transition: 'color 400ms' }}>{head}</div>
                {sub && <div className="cf-sub" style={{ fontSize: 34, marginTop: 14, color: current ? 'var(--ink-2)' : 'var(--ink-3)', transition: 'color 400ms' }}>{sub}</div>}
              </div>
            </div>
          </Reveal>
        );
      })}
    </>
  );
}
