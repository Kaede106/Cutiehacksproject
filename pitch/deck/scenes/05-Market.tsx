import { Reveal, Scene, useScene } from 'beatdeck';
import { Eyebrow } from '../ui';

/**
 * USDA NASS, "Citrus Fruits 2025 Summary" (August 2026), 2025-26 season, value of production
 * (packinghouse-door equivalent) and bearing acres. See reference/brief.md → Market.
 * This is the value of the crop CutieFarm watches over, not CutieFarm's revenue.
 */
const LAYERS = [
  { tag: 'TAM', what: 'US citrus', value: '$3.15B', acres: '428,400 bearing acres', r: 400 },
  { tag: 'SAM', what: 'California citrus', value: '$2.73B', acres: '267,400 bearing acres', r: 316 },
  { tag: 'SOM', what: 'California oranges, where we start', value: '$722M', acres: '133,500 bearing acres', r: 223 },
];

/** Circles are bottom-aligned; radius ∝ √acres, so the areas compare honestly. */
const CX = 1400, BOTTOM = 960;

function Market_() {
  const { here, b } = useScene();
  return (
    <>
      <Eyebrow on={here}>The market · value of the crop we watch</Eyebrow>

      {LAYERS.map((l, i) => {
        const on = here && b >= i;
        const current = here && b === i;
        const ink = current ? 'var(--accent)' : 'var(--ink-3)';
        return (
          <div key={l.tag} style={{
            position: 'absolute', left: CX - l.r, top: BOTTOM - 2 * l.r, width: 2 * l.r, height: 2 * l.r, borderRadius: '50%',
            border: `${current ? 3 : 2}px solid ${ink}`,
            background: i === 2 ? 'rgba(242, 135, 28, 0.16)' : 'transparent',
            opacity: on ? 1 : 0, transform: `scale(${on ? 1 : 0.94})`, transformOrigin: '50% 100%',
            transition: 'opacity 600ms var(--ease), transform 900ms var(--ease), border-color 400ms',
          }} />
        );
      })}
      {LAYERS.map((l, i) => (
        <Reveal key={`t${l.tag}`} on={here && b >= i} x={CX - 60} y={BOTTOM - 2 * l.r + 30} delay={300}>
          <div className="t-meta" style={{ fontSize: 26, width: 120, textAlign: 'center', color: here && b === i ? 'var(--accent)' : 'var(--ink-3)', transition: 'color 400ms' }}>{l.tag}</div>
        </Reveal>
      ))}

      {LAYERS.map((l, i) => {
        const current = here && b === i;
        return (
          <Reveal key={l.tag} on={here && b >= i} x={150} y={210 + i * 250}>
            <div className="t-meta" style={{ fontSize: 24, color: current ? 'var(--accent)' : 'var(--ink-3)', transition: 'color 400ms' }}>{l.tag} · {l.what}</div>
            <div className="t-statement" style={{ fontSize: 130, marginTop: 14, color: current ? 'var(--ink)' : 'var(--ink-3)', transition: 'color 400ms' }}>{l.value}</div>
            <div className="cf-note" style={{ fontSize: 24, marginTop: 10, color: current ? 'var(--ink-2)' : 'var(--ink-3)', transition: 'color 400ms' }}>{l.acres}</div>
          </Reveal>
        );
      })}

      <Reveal on={here} x={150} y={975} delay={600}>
        <div className="cf-note" style={{ fontSize: 18 }}>
          USDA NASS, Citrus Fruits 2025 Summary (Aug 2026), 2025-26 season · value of production, not our revenue
        </div>
      </Reveal>
    </>
  );
}

/** 05 MARKET — TAM / SAM / SOM as the value of the citrus crop (USDA NASS 2025-26), nested circles. */
export const Market = () => <Scene index={4}><Market_ /></Scene>;
