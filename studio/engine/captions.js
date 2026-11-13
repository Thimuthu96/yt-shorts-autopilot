// Captions: one word at a time, centred at 58 % of the frame height, white with a dark outline and a soft shadow,
// no box. Pure timing (captionWord, captionText) plus drawCaption(ctx, word), which paints onto a 2D canvas laid
// over the 3D view. No DOM access at import time.
import { INK } from "./core.js";

export const CAPTION = { y: 0.58, size: 70, fill: "#FFFFFF", outline: INK, stroke: 10, maxWidth: 0.9 };

// The word whose [s, e) holds t. Inside a beat a pause keeps the previous word until the next one starts;
// before a beat's first word, and outside every beat, there is no caption.
export function captionWord(timeline, t) {
  const beats = (timeline && timeline.beats) || [];
  const b = beats.find((x) => t >= x.start && t < x.end);
  if (!b) return "";
  let word = "";
  for (const w of b.words || []) {
    if (w.s > t) break;
    word = w.w;
  }
  return word;
}

// What is shown: trailing commas and full stops go ("code." -> "code"); ? and ! stay, inner commas (1,000) stay.
export const captionText = (w) => String(w || "").replace(/[.,;:]+$/u, "");

// Paints the word on a canvas the size of the frame (ctx already scaled to 1080 x 1920 design pixels).
export function drawCaption(ctx, word, W = 1080, H = 1920) {
  ctx.clearRect(0, 0, W, H);
  const text = captionText(word);
  if (!text) return;
  let size = CAPTION.size;
  ctx.font = `700 ${size}px Fredoka`;
  const wide = ctx.measureText(text).width;
  if (wide > W * CAPTION.maxWidth) size = Math.floor((size * W * CAPTION.maxWidth) / wide);
  ctx.font = `700 ${size}px Fredoka`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  ctx.miterLimit = 2;
  const x = W / 2, y = H * CAPTION.y;
  // the outline is drawn twice as wide as `stroke` because half of a stroke falls inside the glyph
  ctx.save();
  ctx.shadowColor = "rgba(10, 6, 30, 0.55)";
  ctx.shadowBlur = 16;
  ctx.shadowOffsetY = 6;
  ctx.strokeStyle = CAPTION.outline;
  ctx.lineWidth = CAPTION.stroke * 2;
  ctx.strokeText(text, x, y);
  ctx.restore();
  ctx.fillStyle = CAPTION.fill;
  ctx.fillText(text, x, y);
}
