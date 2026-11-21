import './styles.css';
import { mountScanner } from './scanner/index.js';
import qrcode from 'qrcode-generator';

const root = document.getElementById('scanner-root');
if (root) mountScanner(root);

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

// Hero: one pass of the camera over the grove. Each orange's frame appears as the line reaches it,
// then the example morning message arrives.
// Without JS or with reduced motion the frames are simply there.
function scanGrove() {
  const grove = document.querySelector('[data-grove]');
  if (!grove || reduceMotion.matches) return;

  const sweep = 2000;
  const delay = 350;
  const box = grove.getBoundingClientRect();
  if (!box.width) return;

  for (const mark of grove.querySelectorAll('.mark')) {
    const r = mark.getBoundingClientRect();
    const centre = (r.left + r.width / 2 - box.left) / box.width;
    const at = Math.min(1, Math.max(0, centre));
    mark.style.animationDelay = `${Math.round(delay + sweep * at)}ms`;
  }

  const hero = grove.closest('.hero') || grove;
  hero.style.setProperty('--sweep', `${sweep}ms`);
  hero.style.setProperty('--sweep-delay', `${delay}ms`);
  grove.classList.add('is-scanning');
  hero.classList.add('is-scanning');

  // Remove the overlay elements' animation state once done so nothing sits on top of the art.
  window.setTimeout(() => grove.classList.add('is-scanned'), delay + sweep + 400);
}

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

scanGrove();
wireJumps();
wireTelegram();
