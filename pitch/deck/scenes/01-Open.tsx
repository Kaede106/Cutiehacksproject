import { Reveal, Scene, swap, useScene } from 'beatdeck';
import { config } from '../deck.config';
import grove from '../assets/grove-1400.webp';

function Open_() {
  const { here, b } = useScene();
  const title = here && b === 1;
  return (
    <>
      {/* 01.1 standby: nothing but a quiet orange mark */}
      <div style={{ position: 'absolute', left: 948, top: 528, width: 24, height: 24, borderRadius: 12, background: 'var(--accent)', opacity: here && b === 0 ? 1 : 0, transition: 'opacity 400ms' }} />

      {/* 01.2 title over a band of the grove photo */}
      <div className="cf-photo band" style={{ top: 640, height: 440, opacity: title ? 1 : 0, transition: swap(title, 1400, 200) }}>
        <img src={grove} alt="" />
      </div>
      <Reveal on={title} x={160} y={150}>
        <div className="t-eyebrow">{config.event} · {config.author}</div>
      </Reveal>
      <Reveal on={title} x={146} y={214} delay={120} ms={1100}>
        <div className="t-statement" style={{ fontSize: 290 }}>
          Cutie<span style={{ color: 'var(--accent)' }}>Farm</span>
        </div>
      </Reveal>
      <Reveal on={title} x={160} y={512} delay={380}>
        <div className="cf-sub" style={{ fontSize: 52, color: 'var(--ink)' }}>{config.subtitle}</div>
      </Reveal>
    </>
  );
}

/** 01 OPEN — standby, then the title. */
export const Open = () => <Scene index={0}><Open_ /></Scene>;
