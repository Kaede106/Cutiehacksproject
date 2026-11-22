import { defineConfig, mergeConfig, type UserConfig } from 'vite';
import base from './vite.config';

/**
 * Single-file build: every asset (fonts, the photo, CSS, all JS chunks) inlined, so `tools/single-html.mjs`
 * can fold it into one HTML file that opens straight from disk. `npm run build:html`.
 */
export default defineConfig((env) => {
  const b = (typeof base === 'function' ? base(env) : base) as UserConfig;
  return mergeConfig(b, {
    build: {
      outDir: 'dist-single',
      assetsInlineLimit: 100_000_000,
      cssCodeSplit: false,
      modulePreload: false,
      rollupOptions: { output: { inlineDynamicImports: true } },
    },
  });
});
