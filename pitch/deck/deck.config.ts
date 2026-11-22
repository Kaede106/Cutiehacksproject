/**
 * Everything that may need changing five minutes before going on stage lives here.
 * After editing, rebuild (`npm run build` / `npm run present`).
 */
export const config = {
  title: 'CutieFarm',
  /** The tagline under the title. */
  subtitle: 'Know which oranges to pick, which are sick, and when to water.',
  author: 'The CutieFarm team',
  event: 'Cutiehacks 2026',
  /** Destination of the QR on the closing screen: the CutieFarm website. */
  qrUrl: 'https://cutiehacksproject.vercel.app',
  /** Shown next to the QR. */
  qrLabel: 'cutiehacksproject.vercel.app',
  /** Shown as text on the closing screen (one QR only, so `npm run verify` decodes it unambiguously). */
  bot: 't.me/CutieFarmGroveBot',
  botHandle: '@CutieFarmGroveBot',
  repo: 'github.com/Kaede106/Cutiehacksproject',
} as const;
