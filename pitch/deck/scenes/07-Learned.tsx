import { Scene, useScene } from 'beatdeck';
import { Eyebrow, StackedRows } from '../ui';

const ROWS: [string, string][] = [
  ['The STM32 board fought us.', 'So we switched to an Arduino.'],
  ['Colour is fragile.', 'So YOLO finds the fruit first.'],
  ['A public bot has to be safe.', 'Rate limits · no group chats · no secrets in logs'],
  ['Demo data says it is demo data.', 'Honest labelling until the hardware is wired in.'],
];

function Learned_() {
  const { here, b } = useScene();
  return (
    <>
      <Eyebrow on={here}>Challenges · what we learned</Eyebrow>
      <StackedRows here={here} b={b} first={0} rows={ROWS} y={220} step={195} size={84} />
    </>
  );
}

/** 07 WHAT WE LEARNED — four challenges, one per beat. */
export const Learned = () => <Scene index={6}><Learned_ /></Scene>;
