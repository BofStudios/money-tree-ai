/* Screenshots in the chat (desktop 10.0).
 *
 * Up to three images per question: the paperclip, paste (Ctrl+V) or drag
 * and drop. Each one is shrunk to 1600 px JPEG in the page, sent with that
 * one question to a free vision model, and then forgotten: nothing is saved.
 */

const MAX = 3;
const EDGE = 1600;
const $ = (id) => document.getElementById(id);
let pending = [];          // data URIs

function shrink(file) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith("image/")) { reject(new Error("not an image")); return; }
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, EDGE / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("unreadable image")); };
    img.src = url;
  });
}

function draw() {
  const strip = $("shotStrip");
  if (!strip) return;
  strip.innerHTML = pending.map((src, i) =>
    `<figure><img src="${src}" alt=""><button type="button" data-unshot="${i}" aria-label="Remove">×</button></figure>`).join("");
}

async function add(files) {
  for (const f of files) {
    if (pending.length >= MAX) break;
    try { pending.push(await shrink(f)); } catch { /* not an image: ignored */ }
  }
  draw();
}

function setup() {
  const form = $("askForm");
  if (!form || $("shotPick")) return;
  const input = document.createElement("input");
  input.type = "file";
  input.accept = "image/png,image/jpeg,image/webp";
  input.multiple = true;
  input.hidden = true;
  input.id = "shotPick";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "shot-btn";
  btn.setAttribute("aria-label", "Add a screenshot");
  btn.title = "Screenshot";
  btn.innerHTML = '<svg viewBox="0 0 20 20"><path d="M13.5 6.5 7.6 12.4a1.6 1.6 0 0 0 2.3 2.3l6-6a3.2 3.2 0 0 0-4.5-4.5l-6.1 6.1a4.8 4.8 0 0 0 6.8 6.8l4.4-4.4"/></svg>';
  btn.onclick = () => input.click();
  input.onchange = () => { add([...input.files]); input.value = ""; };
  form.prepend(btn);
  form.append(input);
  const strip = document.createElement("div");
  strip.className = "shot-strip";
  strip.id = "shotStrip";
  form.parentNode.insertBefore(strip, form);
  strip.onclick = (e) => {
    const b = e.target.closest("[data-unshot]");
    if (b) { pending.splice(Number(b.dataset.unshot), 1); draw(); }
  };

  const rail = form.closest("aside") || document;
  rail.addEventListener("paste", (e) => {
    const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
    if (files.length) { e.preventDefault(); add(files); }
  });
  rail.addEventListener("dragover", (e) => { if (e.dataTransfer?.types?.includes("Files")) e.preventDefault(); });
  rail.addEventListener("drop", (e) => {
    const files = [...(e.dataTransfer?.files || [])].filter((f) => f.type.startsWith("image/"));
    if (files.length) { e.preventDefault(); add(files); }
  });
}

/* chart.js asks for the images when the question is sent, and they are gone. */
window.mtShots = {
  take() { const out = pending; pending = []; draw(); return out; },
  count() { return pending.length; },
};

setup();
