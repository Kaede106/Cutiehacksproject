# Scanner module

The in-browser orange scanner. It reads the centre square of a webcam frame (or of a sample image) and labels it unripe, ripening, ready to pick, possible mold, or no orange. It runs entirely on the device. The contract with the page (`mountScanner`, the `cutiefarm:reading` event, the `--cf-*` tokens) is in `web/PRODUCT.md`.

## Files

| File | What it does |
|---|---|
| `index.js` | `mountScanner(rootEl, options) -> { destroy }`. Builds the UI inside `rootEl`, runs the camera loop, the sample picker and the state panels, and dispatches `cutiefarm:reading`. |
| `scanner.css` | All styles, scoped under `.cf-scanner`. It uses only `var(--cf-*, fallback)` tokens. |
| `classifier.js` | The classifier interface and the default colour heuristic (`createColorClassifier`). Everything except the factory is a pure function on `{ data, width, height }`. |
| `smoothing.js` | Smooths readings over time (EMA, about 0.4 s time constant, with hysteresis) so the label doesn't flicker. It works with any classifier. |
| `camera.js` | Feature detection (secure context, `getUserMedia`), the permission query, opening and stopping the stream, and mapping errors to states. |
| `samples.js` | Five procedural sample images (green, turning, deep orange, spotted with mold, empty crate), rendered per pixel with no canvas so Node can test them. |
| `classifier.test.mjs` | Node test: synthetic buffers, the five samples, the ROI maths and the smoother. |
| `dev.html` | Standalone harness with token values, a dark-mode toggle, an event log and a mount/destroy stress button. |

## Run

```sh
cd web
node src/scanner/classifier.test.mjs   # exits 1 on any failure
npx vite                               # then open http://localhost:5173/src/scanner/dev.html
```

The camera needs HTTPS or `localhost`. Over a LAN IP on plain http the scanner shows the "needs a secure page" message, and the samples still work.

## Classifier interface

```js
const classifier = {
  description: 'Shown under the reading (optional)',
  async classify(source) {
    // source: ImageData (128 x 128 crop of the centre square), a canvas, or { data, width, height }
    return {
      label: 'unripe' | 'ripening' | 'ripe' | 'mold' | 'none',
      confidence: 0..1,
      scores: { unripe, ripening, ripe, mold },   // about 1 in total
      regions: [{ x, y, w, h, label }],           // optional, 0..1 in source coordinates
    };
  },
};
mountScanner(root, { classifier });
```

The scanner calls `classify` about 6 times a second, never twice at once. It smooths the results, shows `regions` as boxes when the label is mold, and fires the event only when the label or the confidence level (high, medium or low) changes. If `classify` throws, the scanner stops the camera and shows "The reading failed".

### Plugging in a TF.js or ONNX model

Write a factory that loads the model once and returns an object with the shape above.

- TF.js: `const model = await tf.loadGraphModel('/models/orange/model.json')`. In `classify`, use `tf.tidy` to run `tf.browser.fromPixels(source)`, then `resizeBilinear` to the input size, then normalise the way the training did. Then `model.predict(...)`, then `softmax`, and read the values with `await t.data()`.
- ONNX Runtime Web: `const session = await ort.InferenceSession.create('/models/orange.onnx')`. Convert the RGBA buffer into a float32 NCHW tensor, then call `session.run({ [inputName]: tensor })`.
- Map the outputs onto the four `scores` keys. Return `none` when a background class wins or the top score is below a threshold. Use the top score, or the margin over the second one, as `confidence`.
- Load the model before mounting, or show your own loading state. `mountScanner` takes a ready classifier.
- Put the model files in `public/`, so they are served locally and no frame leaves the device.

## How the colour heuristic decides

The full set of thresholds is in `THRESHOLDS` in `classifier.js`.

- Pixels it ignores:
  - Dark pixels (V < 0.2).
  - Clipped highlights (V > 0.965 and S < 0.12).
  - Greys.
  - Skin and brown wood. These are caught by a YCbCr box (Cb 77–127, Cr 133–173) checked on warm hues with S < 0.72. Saturated orange peel has Cb below 77, so it falls outside the box.
- Fruit pixels: hue 5–145°, S ≥ 0.33, V ≥ 0.22. Each one is split by hue between orange (up to 36°), yellow (48–60°) and green (76° and up), with linear blends in between.
- How hue becomes scores:
  - The orange share becomes "ready to pick", yellow becomes "ripening" and green becomes "unripe".
  - When green and orange appear on the same fruit, the smaller of the two shares moves into "ripening", weighted 1.5×.
- Mold:
  - Mold pixels are white fuzz (S ≤ 0.2, V ≥ 0.62) and blue-green pixels (hue 150–235°, S 0.1–0.65).
  - These pixels count only inside 16 × 16 grid cells that the fruit surrounds: at least 5 of 8 rays from the cell must reach a fruit cell. So a white table or wall beside the orange is not read as mold.
  - The evidence is (white + 2.5 × blue-green) ÷ fruit area. It ramps from 3% to 10%.
- No orange: when fruit covers less than 10% of the square.
- Confidence: coverage (from 10% to 40%) multiplied by the margin between the top two scores. It is shown only as "High", "Medium" or "Low".

## Known limitations

- **It is a colour heuristic, not a trained model.** Anything orange in the square reads as a ripe orange: a ball, a shirt or a carrot. Anything green reads as unripe, including leaves.
- **Lighting and white balance.** Warm indoor light pushes green peel towards yellow, and cool LED light pushes orange towards yellow. Coloured stage lighting breaks it. Even, white light works best.
- **Skin tones.** The YCbCr filter removes most skin, but very saturated dark skin (S > 0.72) can pass as orange peel. A dull, brownish orange in dim warm light can be filtered out as skin.
- **Mold.** It detects white fuzz and blue-green patches. It does not catch olive-green *Penicillium digitatum* spores, brown rot or soft spots. Strong specular highlights that are not clipped can look like fuzz on very glossy fruit.
- **Region of interest.** It reads only the centre square, 60% of the frame height. A mold patch at the edge of the square may be missed.
- **The samples are synthetic.** The test proves the code is consistent with itself. It says nothing about accuracy on real oranges, and the page should not claim any.

## Left open

- No snapshot or freeze-frame.
- No choice of camera: it asks for the rear camera when there is one, otherwise the default.
- No browser automation tests. The checks so far are the Node test and a manual check of `dev.html`.
