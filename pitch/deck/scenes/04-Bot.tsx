import { Arrow, NodeBox, Reveal, Scene, useScene, type Rect } from 'beatdeck';
import { config } from '../deck.config';
import { Bubble, Eyebrow, ExampleNote } from '../ui';

const R: Record<string, Rect> = {
  vision: { x: 150, y: 260, w: 420, h: 130 },
  water: { x: 150, y: 560, w: 420, h: 130 },
  bot: { x: 800, y: 370, w: 380, h: 210 },
  grower: { x: 1450, y: 410, w: 320, h: 130 },
};

const small = { fontSize: 22, fontWeight: 400, color: 'var(--ink-2)', marginTop: 6 } as const;

/** Right edge of user bubbles, so they sit on the right like a chat. */
const RIGHT = 1770;

function Bot_() {
  const { here, b } = useScene();
  const at = (k: number) => here && b === k;
  const past = (k: number) => here && b > k;
  const diagram = at(0);
  const label = (k: number, text: string) => <Eyebrow on={at(k)} out={past(k)}>{text}</Eyebrow>;
  return (
    <>
      {/* 04.1 everything lands in one chat */}
      <Eyebrow on={diagram} out={past(0)}>One place to ask</Eyebrow>
      <NodeBox rect={R.vision} on={diagram} kind="ripe? healthy?" value="Camera + ML" />
      <NodeBox rect={R.water} on={diagram} delay={100} kind="water?" value="Watering plan" />
      <Arrow from={R.vision} to={R.bot} on={diagram} delay={300} />
      <Arrow from={R.water} to={R.bot} on={diagram} delay={300} />
      <NodeBox rect={R.bot} on={diagram} delay={450} tone="hot" kind="Telegram"
        value={<><div style={{ fontSize: 40 }}>Bot</div><div style={small}>{config.botHandle}</div></>} />
      <Arrow from={{ x: 1180, y: 450 }} to={{ x: 1450, y: 450 }} on={diagram} delay={700} tone="hot" />
      <Arrow from={{ x: 1450, y: 505 }} to={{ x: 1180, y: 505 }} on={diagram} delay={800} />
      <NodeBox rect={R.grower} on={diagram} delay={850} kind="in their pocket" value="Grower" />
      <Reveal on={diagram} out={past(0)} x={150} y={800} delay={900}>
        <div className="t-statement" style={{ fontSize: 110 }}>Everything lands in one chat.</div>
      </Reveal>

      {/* 04.2 the 9:00 summary */}
      {label(1, '9:00 every morning · example')}
      <Reveal on={at(1)} out={past(1)} x={150} y={240} delay={150}>
        <Bubble who="bot" time="9:00">
          <span style={{ color: 'var(--accent)' }}>3 ready to pick</span>, 5 ripening.<br />
          Water on Thursday: hot, dry week ahead,<br />
          so twice a week for now.
        </Bubble>
      </Reveal>

      {/* 04.3 ready-to-pick alert */}
      {label(2, 'Instant alert · example')}
      <Reveal on={at(2)} out={past(2)} x={150} y={280} delay={150}>
        <Bubble who="bot" time="alert">
          <span style={{ color: 'var(--accent)' }}>More oranges are ready to pick.</span>
        </Bubble>
      </Reveal>
      <Reveal on={at(2)} out={past(2)} x={150} y={620} delay={450}>
        <div className="cf-sub">As soon as the camera sees them, not at the next walk.</div>
      </Reveal>

      {/* 04.4 a question in Spanish */}
      {label(3, 'Ask in your language · text or voice · example')}
      <Reveal on={at(3)} out={past(3)} x={RIGHT - 760} y={240} delay={150}>
        <div style={{ width: 760 }}><Bubble who="user" time="grower">¿Y las de la izquierda?</Bubble></div>
      </Reveal>
      <Reveal on={at(3)} out={past(3)} x={150} y={500} delay={600}>
        <Bubble who="bot" time="CutieFarm">
          <span style={{ color: 'var(--ink-2)' }}>Answers back in Spanish,</span><br />
          <span style={{ color: 'var(--ink-2)' }}>by text, or by voice for a voice note.</span>
        </Bubble>
      </Reveal>
      <Reveal on={at(3)} out={past(3)} x={150} y={860} delay={800}>
        <div className="cf-note" style={{ fontSize: 24, color: 'var(--ink-2)' }}>Also: send a photo of an orange, get its state.</div>
      </Reveal>

      {/* 04.5 /week */}
      {label(4, 'Logging · example')}
      <Reveal on={at(4)} x={RIGHT - 760} y={240} delay={150}>
        <div style={{ width: 760 }}><Bubble who="user" time="grower"><span className="cf-mono" style={{ fontSize: 50 }}>/week</span></Bubble></div>
      </Reveal>
      <Reveal on={at(4)} x={150} y={500} delay={600}>
        <Bubble who="bot" time="CutieFarm">
          Your week: what you <span className="cf-mono" style={{ fontSize: 48, color: 'var(--accent)' }}>/picked</span> and <span className="cf-mono" style={{ fontSize: 48, color: 'var(--accent)' }}>/watered</span>,<br />
          plus a <span style={{ color: 'var(--accent)' }}>harvest forecast</span>.
        </Bubble>
      </Reveal>

      <ExampleNote on={here && b >= 1} x={150} y={960}>Examples · the bot currently runs on clearly labelled demo data</ExampleNote>
    </>
  );
}

/** 04 THE BOT — everything lands in one Telegram chat; four example exchanges. */
export const Bot = () => <Scene index={3}><Bot_ /></Scene>;
