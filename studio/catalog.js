// Writes studio/catalog.json: every name a story may use, read by the Python validator (autopilot/story.py).
// Usage: node studio/catalog.js
// Each registry module exports catalog() -> {key: [names]}; a new registry is one more line in REGISTRIES.
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const REGISTRIES = ["engine/world.js", "engine/cast.js", "engine/camera.js", "engine/fx.js", "engine/signs.js", "engine/events.js", "engine/actions.js"];

// Keys no registry owns yet stay empty; the constants below are owned here.
const BASE = {
  sets: [], moods: [], props: [], poses: [], exprs: [], motions: [], enters: [], fx: [], cam_moves: [], sign_styles: [], cam_frames: [],
  transitions: [], looks: [], costume_keys: [], costumes: [], anims: [], events: [], event_fields: {}, acts: [], act_fields: {}, surfaces: [],
  sfx: ["whoosh", "boom", "splash", "impact", "pop", "ding", "crackle", "creak"],
};

async function build() {
  const out = { ...BASE };
  for (const rel of REGISTRIES) {
    const mod = await import(pathToFileURL(path.join(__dirname, rel)).href);
    Object.assign(out, mod.catalog());
  }
  return out;
}

if (require.main === module) {
  build()
    .then((cat) => {
      const file = path.join(__dirname, "catalog.json");
      fs.writeFileSync(file, JSON.stringify(cat, null, 2) + "\n");
      console.log(`wrote ${path.relative(process.cwd(), file)}: ${cat.sets.length} sets, ${cat.props.length} props, ${cat.moods.length} moods`);
    })
    .catch((e) => { console.error(e.stack || e.message); process.exit(1); });
}

module.exports = { build };
