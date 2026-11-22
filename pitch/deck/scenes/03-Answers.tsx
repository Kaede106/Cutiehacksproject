import { Arrow, NodeBox, Reveal, Scene, useScene, type Rect } from 'beatdeck';
import { BigQuestion, Bubble, Eyebrow, ExampleNote } from '../ui';

const small = { fontSize: 22, fontWeight: 400, color: 'var(--ink-2)', marginTop: 6 } as const;

const RIPE: Record<string, Rect> = {
  webcam: { x: 150, y: 300, w: 320, h: 140 },
  yolo: { x: 600, y: 280, w: 520, h: 180 },
  colour: { x: 1250, y: 280, w: 520, h: 180 },
};
const STATES: [string, string][] = [['unripe', 'var(--ink-3)'], ['ripening', 'var(--ink-2)'], ['ready to pick', 'var(--accent)']];

const SICK: Record<string, Rect> = {
  orange: { x: 150, y: 400, w: 320, h: 140 },
  cnn: { x: 600, y: 370, w: 520, h: 200 },
  healthy: { x: 1290, y: 240, w: 480, h: 110 },
  canker: { x: 1290, y: 415, w: 480, h: 110 },
  melanose: { x: 1290, y: 590, w: 480, h: 110 },
};

const WATER: Record<string, Rect> = {
  arduino: { x: 150, y: 280, w: 400, h: 220 },
  forecast: { x: 150, y: 600, w: 400, h: 140 },
  plan: { x: 820, y: 420, w: 560, h: 200 },
};

const LIMITS = ['max seconds per run', 'a cooldown between runs', 'a daily cap', 'never on wet soil'];

function Answers_() {
  const { here, b } = useScene();
  const at = (k: number) => here && b === k;
  const past = (k: number) => here && b > k;
  const ripe = here && (b === 1 || b === 2);
  const sick = at(4);
  const water = at(7);
  return (
    <>
      {/* 03.1–03.3 RIPE? */}
      <BigQuestion on={at(0)} out={past(0)} eyebrow="Answer 1 of 3" text="Is it ripe?" sub="A laptop webcam watches the tree." />
      <Eyebrow on={ripe} out={past(2)}>Ripe? · find, then judge</Eyebrow>
      <NodeBox rect={RIPE.webcam} on={ripe} kind="camera" value="Laptop webcam" tone={b === 2 ? 'dim' : 'normal'} />
      <Arrow from={RIPE.webcam} to={RIPE.yolo} on={ripe} delay={200} tone={b === 1 ? 'hot' : 'normal'} />
      <NodeBox rect={RIPE.yolo} on={ripe} delay={350} tone={b === 1 ? 'hot' : 'normal'} kind="Ultralytics YOLO" value="Finds each orange" />
      <Reveal on={at(1)} out={past(1)} x={150} y={620} delay={600}>
        <div className="t-statement" style={{ fontSize: 120 }}>Find the fruit first.</div>
      </Reveal>
      <Arrow from={RIPE.yolo} to={RIPE.colour} on={at(2)} delay={100} tone="hot" />
      <NodeBox rect={RIPE.colour} on={at(2)} delay={250} tone="hot" kind="peel colour" value="How orange is it?" />
      {STATES.map(([label, color], i) => (
        <Reveal key={label} on={at(2)} out={past(2)} x={160 + i * 560} y={640} delay={500 + i * 150}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
            <span className="cf-dot" style={{ background: color }} />
            <span className="t-statement" style={{ fontSize: 64 }}>{label}</span>
          </div>
        </Reveal>
      ))}

      {/* 03.4–03.6 HEALTHY? */}
      <BigQuestion on={at(3)} out={past(3)} eyebrow="Answer 2 of 3" text="Is it healthy?" sub="Our own model, trained on citrus images." />
      <Eyebrow on={sick} out={past(4)}>Healthy? · our own CNN</Eyebrow>
      <NodeBox rect={SICK.orange} on={sick} kind="from YOLO" value="Each orange" />
      <Arrow from={SICK.orange} to={SICK.cnn} on={sick} delay={200} />
      <NodeBox rect={SICK.cnn} on={sick} delay={350} tone="hot" kind="PyTorch CNN · ours"
        value={<><div>Trained on citrus</div><div style={small}>healthy or diseased?</div></>} />
      <Arrow from={SICK.cnn} to={SICK.healthy} on={sick} delay={650} />
      <Arrow from={SICK.cnn} to={SICK.canker} on={sick} delay={700} tone="hot" />
      <Arrow from={SICK.cnn} to={SICK.melanose} on={sick} delay={750} tone="hot" />
      <NodeBox rect={SICK.healthy} on={sick} delay={800} kind="label" value="healthy" />
      <NodeBox rect={SICK.canker} on={sick} delay={880} tone="hot" kind="diseased" value="citrus canker" />
      <NodeBox rect={SICK.melanose} on={sick} delay={960} tone="hot" kind="diseased" value="melanose" />

      <Eyebrow on={at(5)} out={past(5)} y={250}>The bot says · example message</Eyebrow>
      <Reveal on={at(5)} out={past(5)} x={150} y={330} delay={150}>
        <Bubble who="bot" time="CutieFarm">
          <span style={{ color: 'var(--accent)' }}>1 orange may have citrus canker:</span><br />take a look before it spreads.
        </Bubble>
      </Reveal>
      <Reveal on={at(5)} out={past(5)} x={150} y={720} delay={450}>
        <div className="cf-sub">Caught on the tree, not weeks later.</div>
      </Reveal>

      {/* 03.7–03.10 WATER? */}
      <BigQuestion on={at(6)} out={past(6)} eyebrow="Answer 3 of 3" text="Does it need water?" size={190} sub="The soil, the air, and the forecast." />
      <Eyebrow on={water} out={past(7)}>Water? · measure, then forecast</Eyebrow>
      <NodeBox rect={WATER.arduino} on={water} kind="Arduino sensors"
        value={<><div>Soil moisture</div><div>Temperature</div><div>Humidity</div></>} />
      <NodeBox rect={WATER.forecast} on={water} delay={150} kind="forecast" value="Open-Meteo" />
      <Arrow from={WATER.arduino} to={WATER.plan} on={water} delay={350} />
      <Arrow from={WATER.forecast} to={WATER.plan} on={water} delay={400} />
      <NodeBox rect={WATER.plan} on={water} delay={600} tone="hot" kind="watering plan"
        value={<><div>How often</div><div style={small}>and when to water next</div></>} />

      <Eyebrow on={at(8)} out={past(8)}>Water? · the maths</Eyebrow>
      <Reveal on={at(8)} out={past(8)} x={150} y={240}>
        <div className="t-statement" style={{ fontSize: 120, lineHeight: 1.12 }}>
          evapotranspiration<br />
          <span style={{ color: 'var(--ink-2)' }}>×</span> citrus crop coefficient<br />
          <span style={{ color: 'var(--ink-2)' }}>−</span> rain
        </div>
      </Reveal>
      <Reveal on={at(8)} out={past(8)} x={150} y={720} delay={500}>
        <div style={{ width: 1100, height: 2, background: 'var(--hair-strong)' }} />
        <div className="t-statement" style={{ fontSize: 120, marginTop: 40, color: 'var(--accent)' }}>= how often to water</div>
      </Reveal>

      <Eyebrow on={at(9)}>Water? · the pump</Eyebrow>
      <Reveal on={at(9)} x={150} y={230}>
        <div className="t-statement" style={{ fontSize: 150 }}>It can water itself.<br /><span style={{ color: 'var(--accent)' }}>Within limits.</span></div>
      </Reveal>
      {LIMITS.map((l, i) => (
        <Reveal key={l} on={at(9)} x={160 + (i % 2) * 820} y={640 + Math.floor(i / 2) * 120} delay={400 + i * 120}>
          <div className="cf-mono" style={{ fontSize: 44 }}><span style={{ color: 'var(--accent)' }}>■ </span>{l}</div>
        </Reveal>
      ))}
      <ExampleNote on={at(5)} out={past(5)} x={150} y={850}>Example message · the bot currently runs on clearly labelled demo data</ExampleNote>
    </>
  );
}

/** 03 THREE ANSWERS — ripe? (YOLO + peel colour), healthy? (our CNN), water? (sensors + forecast + safe pump). */
export const Answers = () => <Scene index={2}><Answers_ /></Scene>;
