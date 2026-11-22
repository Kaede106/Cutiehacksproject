import { Arrow, NodeBox, Reveal, Scene, useScene, type Rect } from 'beatdeck';
import { Eyebrow } from '../ui';

const R: Record<string, Rect> = {
  camera: { x: 150, y: 300, w: 340, h: 120 },
  sensors: { x: 150, y: 560, w: 340, h: 120 },
  folder: { x: 740, y: 400, w: 440, h: 180 },
  bot: { x: 1430, y: 300, w: 340, h: 120 },
  dashboard: { x: 1430, y: 560, w: 340, h: 120 },
};

const TEAM: [string, string][] = [['2', 'hardware'], ['1', 'ML'], ['1', 'software + integration']];

const STACK: [string, string][] = [
  ['vision', 'OpenCV · Ultralytics YOLO · PyTorch CNN'],
  ['bot', 'python-telegram-bot · OpenAI for chat + voice'],
  ['hardware', 'Arduino + a serial bridge'],
  ['web', 'Vite app on Vercel'],
];

function Built_() {
  const { here, b } = useScene();
  const at = (k: number) => here && b === k;
  const past = (k: number) => here && b > k;
  const diagram = here && b <= 3;
  const from = (k: number) => here && b >= k && b <= 3;
  return (
    <>
      <Eyebrow on={here}>How we built it</Eyebrow>

      {/* 06.1–06.4 the diagram builds node by node */}
      <NodeBox rect={R.folder} on={diagram} tone="hot" kind="append-only files" value={<><div style={{ fontSize: 36 }}>Shared folder</div></>} />
      <NodeBox rect={R.camera} on={from(1)} kind="writes" value="Camera + ML" />
      <NodeBox rect={R.sensors} on={from(1)} delay={120} kind="writes" value="Arduino bridge" />
      <Arrow from={R.camera} to={R.folder} on={from(1)} delay={300} tone={b === 1 ? 'hot' : 'normal'} />
      <Arrow from={R.sensors} to={R.folder} on={from(1)} delay={380} tone={b === 1 ? 'hot' : 'normal'} />
      <NodeBox rect={R.bot} on={from(2)} kind="reads + logs" value="Telegram bot" />
      <NodeBox rect={R.dashboard} on={from(2)} delay={120} kind="reads" value="Dashboard" />
      <Arrow from={R.folder} to={R.bot} on={from(2)} delay={300} tone={b === 2 ? 'hot' : 'normal'} head={false} />
      <Arrow from={R.folder} to={R.dashboard} on={from(2)} delay={380} tone={b === 2 ? 'hot' : 'normal'} />

      <Reveal on={at(0)} out={past(0)} x={150} y={720} delay={400}>
        <div className="t-statement" style={{ fontSize: 110 }}>One shared folder.</div>
      </Reveal>
      <Reveal on={at(1)} out={past(1)} x={150} y={760} delay={500}>
        <div className="cf-sub">Every part appends its own files.</div>
      </Reveal>
      <Reveal on={at(2)} out={past(2)} x={150} y={720} delay={500}>
        <div className="t-statement" style={{ fontSize: 110 }}><span style={{ color: 'var(--accent)' }}>No part calls another.</span></div>
      </Reveal>
      <div style={{ position: 'absolute', left: 120, top: 250, width: 1680, height: 480, border: '2px dashed var(--ink-3)', opacity: at(3) ? 1 : 0, transition: 'opacity 500ms' }} />
      <Reveal on={at(3)} out={past(3)} x={150} y={790} delay={300}>
        <div className="cf-mono" style={{ fontSize: 60 }}>
          <span style={{ color: 'var(--accent)' }}>$ </span>python -m farm
        </div>
        <div className="cf-sub" style={{ fontSize: 36, marginTop: 18 }}>One supervisor command runs them all.</div>
      </Reveal>

      {/* 06.5 four people in parallel */}
      <Reveal on={at(4)} out={past(4)} x={150} y={220}>
        <div className="t-statement" style={{ fontSize: 190 }}>Four people,<br /><span style={{ color: 'var(--accent)' }}>in parallel.</span></div>
      </Reveal>
      {TEAM.map(([n, role], i) => (
        <Reveal key={role} on={at(4)} out={past(4)} x={160 + i * 440} y={680} delay={300 + i * 120}>
          <div className="t-numeral" style={{ fontSize: 150, color: 'var(--ink)' }}>{n}</div>
          <div className="t-meta" style={{ fontSize: 26, marginTop: 24 }}>{role}</div>
        </Reveal>
      ))}

      {/* 06.6 the stack */}
      <Reveal on={at(5)} x={150} y={220}>
        <div className="t-statement" style={{ fontSize: 120 }}>Python, an Arduino, a website.</div>
      </Reveal>
      {STACK.map(([k, v], i) => (
        <Reveal key={k} on={at(5)} x={160} y={440 + i * 130} delay={200 + i * 100}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 40 }}>
            <span className="t-meta" style={{ fontSize: 26, width: 200, color: 'var(--accent)' }}>{k}</span>
            <span className="cf-mono" style={{ fontSize: 46 }}>{v}</span>
          </div>
        </Reveal>
      ))}
    </>
  );
}

/** 06 HOW WE BUILT IT — shared append-only folder built node by node, one command, four people, the stack. */
export const Built = () => <Scene index={5}><Built_ /></Scene>;
