import { defineDeck } from 'beatdeck';
import '../themes/neutral.css';
import './deck.css';
import { config } from './deck.config';
import { SCENES } from './scenes';
import { Open } from './scenes/01-Open';
import { Problem } from './scenes/02-Problem';
import { Answers } from './scenes/03-Answers';
import { Bot } from './scenes/04-Bot';
import { Market } from './scenes/05-Market';
import { Demo } from './scenes/06-Demo';
import { Built } from './scenes/07-Built';
import { Learned } from './scenes/08-Learned';
import { Next } from './scenes/09-Next';
import { Close } from './scenes/10-Close';

/** Every layer of the stage, back to front. All stay mounted; each shows itself for its own scene. */
function Stage() {
  return (
    <>
      <Open />
      <Problem />
      <Answers />
      <Bot />
      <Market />
      <Demo />
      <Built />
      <Learned />
      <Next />
      <Close />
    </>
  );
}

export default defineDeck({
  id: 'cutiefarm',
  title: config.title,
  lang: 'en',
  scenes: SCENES,
  Stage,
  fonts: [
    '400 100px "Inter Variable"', '500 100px "Inter Variable"', '600 100px "Inter Variable"',
    '400 32px "JetBrains Mono Variable"', '600 32px "JetBrains Mono Variable"',
  ],
  qrUrl: config.qrUrl,
});
