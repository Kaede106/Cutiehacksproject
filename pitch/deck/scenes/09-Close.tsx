import { QR, Reveal, Scene, swap, useScene } from 'beatdeck';
import { config } from '../deck.config';
import grove from '../assets/grove-1400.webp';

const LINKS: [string, string][] = [
  ['try it', config.qrLabel],
  ['bot', config.bot],
  ['code', config.repo],
];

function Close_() {
  const { here, b } = useScene();
  const motto = here && b === 0;
  const thanks = here && b === 1;
  return (
    <>
      {/* 09.1 a grove that watches itself, over the grove photo */}
      <div className="cf-photo backdrop" style={{ top: 0, height: 1080, opacity: motto ? 1 : 0, transition: swap(motto) }}>
        <img src={grove} alt="" />
      </div>
      <Reveal on={motto} out={here && b > 0} x={150} y={330} ms={1100}>
        <div className="t-statement" style={{ fontSize: 200 }}>A grove that<br /><span style={{ color: 'var(--accent)' }}>watches itself.</span></div>
      </Reveal>

      {/* 09.2 links, QR, thank you */}
      <Reveal on={thanks} x={150} y={180}>
        <div className="t-statement" style={{ fontSize: 210 }}>Thank you<span style={{ color: 'var(--accent)' }}>.</span></div>
      </Reveal>
      {LINKS.map(([k, v], i) => (
        <Reveal key={k} on={thanks} x={160} y={500 + i * 110} delay={200 + i * 100}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 36 }}>
            <span className="t-meta" style={{ fontSize: 24, width: 110, color: 'var(--accent)' }}>{k}</span>
            <span className="cf-mono" style={{ fontSize: 40 }}>{v}</span>
          </div>
        </Reveal>
      ))}
      <Reveal on={thanks} x={1370} y={250} delay={300}>
        <QR url={config.qrUrl} size={400} />
        <div className="t-meta" style={{ fontSize: 20, marginTop: 24, width: 400, lineHeight: 1.5, textTransform: 'none', letterSpacing: '0.02em' }}>
          In-browser orange scanner: frames never leave your device. Plus a watering simulator.
        </div>
      </Reveal>
      <Reveal on={thanks} x={160} y={900} delay={600}>
        <div className="t-meta" style={{ fontSize: 18, textTransform: 'none', letterSpacing: '0.02em', color: 'var(--ink-3)' }}>
          {config.author} · {config.event} · Photo: Engin Akyurt, Pexels
        </div>
      </Reveal>
    </>
  );
}

/** 09 CLOSE — the motto, then the QR to the website, the bot, the repo and thanks. */
export const Close = () => <Scene index={8}><Close_ /></Scene>;
