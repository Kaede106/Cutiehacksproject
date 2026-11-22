import { Scene, useScene } from 'beatdeck';
import { Eyebrow, StackedRows } from '../ui';

const ROWS: [string, string][] = [
  ['Wire it in for good.', 'The live camera and sensors, permanently.'],
  ['Finish the STM32 port.', 'Back to the board we parked.'],
  ['Turn on automatic watering.', 'After the pump has been tested.'],
];

function Next_() {
  const { here, b } = useScene();
  return (
    <>
      <Eyebrow on={here}>What’s next</Eyebrow>
      <StackedRows here={here} b={b} first={0} rows={ROWS} y={250} step={240} size={110} />
    </>
  );
}

/** 08 WHAT'S NEXT — three next steps, one per beat. */
export const Next = () => <Scene index={8}><Next_ /></Scene>;
