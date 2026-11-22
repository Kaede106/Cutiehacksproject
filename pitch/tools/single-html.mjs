// Folds dist-single/ (built by vite.single.config.ts) into one self-contained HTML file.
import { readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const dir = process.argv[2] ?? 'dist-single';
const out = process.argv[3] ?? join(dir, 'cutiefarm-pitch.html');
let html = readFileSync(join(dir, 'index.html'), 'utf8');

html = html.replace(/<script type="module" crossorigin src="\.\/([^"]+)"><\/script>/g, (_, f) => {
  const js = readFileSync(join(dir, f), 'utf8').replace(/<\/script/gi, '<\/script');
  return `<script type="module">${js}</script>`;
});
html = html.replace(/<link rel="stylesheet" crossorigin href="\.\/([^"]+)">/g, (_, f) => `<style>${readFileSync(join(dir, f), 'utf8')}</style>`);

const left = html.match(/(src|href)="\.\/assets\/[^"]+"/g);
if (left) throw new Error(`not inlined: ${left.join(', ')}`);
writeFileSync(out, html);
console.log(`✓ ${out} (${(Buffer.byteLength(html) / 1024 / 1024).toFixed(2)} MB, one file)`);
