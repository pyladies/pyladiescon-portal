// Builds the served widget from its readable source:
//   npm run build:widget
// frontend/widget/v1.js  ->  portal/static/widget/v1.js (minified)
// The header carries the source's sha256, which tests/speakers/test_widget.py
// checks, so CI notices a source change that was not rebuilt without Node.
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { minify } from "terser";

const source = readFileSync("frontend/widget/v1.js", "utf8");
const digest = createHash("sha256").update(source).digest("hex");
const result = await minify(source, {
  compress: { passes: 2 },
  mangle: true,
  format: { comments: false },
});
const banner =
  `/*! PyLadiesCon program widget v1. Source: frontend/widget/v1.js ` +
  `(sha256 ${digest}); rebuild with npm run build:widget. */\n`;
writeFileSync("portal/static/widget/v1.js", banner + result.code + "\n");
console.log(`portal/static/widget/v1.js: ${Buffer.byteLength(banner + result.code)} bytes`);
