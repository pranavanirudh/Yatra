// Drives the answer console's matcher without a browser.
//
// The Python tests can assert that a number reached the page. They cannot
// assert that asking "what can this not tell me" returns the limitations and
// not the forecast -- and a page that answers the wrong question confidently is
// the failure this project is built against, wearing a friendlier face.
//
// Usage: node tests/ui_probe.js <path-to-yatra.html>
// Reads questions as JSON lines on stdin, writes one JSON object per line:
//   {"q": ..., "asked": ..., "headline": ..., "sources": [...]}

"use strict";

const fs = require("fs");

const page = fs.readFileSync(process.argv[2], "utf8");

// The page carries exactly two script blocks: the payload, then the matcher.
const blocks = [...page.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]);
if (blocks.length !== 2) {
  console.error(`expected 2 script blocks, found ${blocks.length}`);
  process.exit(2);
}

// Minimal DOM. The matcher touches the document only to wire up the input box
// and render; the probe stubs those and keeps the resolver, which is the part
// under test.
const node = () => ({
  value: "",
  innerHTML: "",
  addEventListener() {},
  scrollIntoView() {},
  getAttribute() { return null; },
  closest() { return null; },
});
const stubs = { q: node(), go: node(), answer: node() };

globalThis.document = {
  getElementById: (id) => stubs[id] || node(),
  addEventListener() {},
};
globalThis.window = globalThis;

(0, eval)(blocks[0]);
(0, eval)(blocks[1]);

let buffer = "";
process.stdin.on("data", (chunk) => (buffer += chunk));
process.stdin.on("end", () => {
  for (const line of buffer.split("\n")) {
    const question = line.trim();
    if (!question) continue;
    let result;
    try {
      result = globalThis.__resolve(question);
    } catch (err) {
      result = { asked: "THREW", headline: String(err), sources: [] };
    }
    process.stdout.write(
      JSON.stringify({
        q: question,
        asked: result ? result.asked : null,
        headline: result ? result.headline : null,
        body: result ? result.body : null,
        caveats: result ? result.caveats : [],
        sources: result ? result.sources : [],
      }) + "\n"
    );
  }
});
