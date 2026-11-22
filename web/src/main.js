import { mountScanner } from './scanner/index.js';
import qrcode from 'qrcode-generator';

const root = document.getElementById('scanner-root');
if (root) mountScanner(root);

// "Scan an orange" moves focus to the demo heading so keyboard users land in the right place.
function wireJumps() {
  for (const link of document.querySelectorAll('[data-jump]')) {
    link.addEventListener('click', () => {
      const target = document.getElementById('demo-title');
      if (target) window.setTimeout(() => target.focus({ preventScroll: true }), 0);
    });
  }
}

// "Get this message on Telegram": shown only once the bot exists (VITE_TELEGRAM_BOT is its username).
// The ?start=landing payload tells the bot the visitor came from this page.
function wireTelegram() {
  const bot = (import.meta.env.VITE_TELEGRAM_BOT || '').replace(/^@/, '').trim();
  const box = document.querySelector('[data-telegram-cta]');
  if (!box || !/^[A-Za-z0-9_]{5,32}$/.test(bot)) return;
  const url = `https://t.me/${bot}?start=landing`;
  box.querySelector('[data-telegram-link]').href = url;
  const qrBox = box.querySelector('[data-telegram-qr]');
  const qr = qrcode(0, 'M');
  qr.addData(url);
  qr.make();
  qrBox.innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  box.hidden = false;
}

wireJumps();
wireTelegram();
