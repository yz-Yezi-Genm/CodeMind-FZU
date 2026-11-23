import { requireElement } from '../shared/dom';

const gate = requireElement<HTMLElement>('#demo-entry');
const canvas = requireElement<HTMLCanvasElement>('#pointer-field');
const ctx = canvas.getContext('2d');
const reduce = matchMedia('(prefers-reduced-motion: reduce)');
const finePointer = matchMedia('(any-pointer: fine)');

type Point = { x: number; y: number };
type Tile = Point & { size: number; opacity: number; phase: number };
let width = 0;
let height = 0;
let pixels: Tile[] = [];
let target: Point | null = null;
let cursor: Point | null = null;
let strength = 0;
let animation = 0;

function arrange(): void {
  pixels = [];
  const spacing = width < 760 ? 17 : 18;
  for (let y = spacing / 2; y < height; y += spacing) {
    for (let x = spacing / 2; x < width; x += spacing) {
      const phase = Math.sin(x * 73.3 + y * 18.7) * 43758.5;
      const noise = phase - Math.floor(phase);
      const distance = Math.hypot((x / width - .50) * 1.4, y / height - .55);
      const density = Math.max(.03, .80 - distance);
      pixels.push({ x, y, phase: noise, size: 1 + noise * 4, opacity: noise < density ? density * .16 : 0 });
    }
  }
}

function draw(): void {
  if (!ctx || !width || !height) return;
  ctx.clearRect(0, 0, width, height);
  const radius = 155;
  ctx.fillStyle = '#a91d35';

  for (const tile of pixels) {
    const dx = cursor ? cursor.x - tile.x : 0;
    const dy = cursor ? cursor.y - tile.y : 0;
    const distance = Math.hypot(dx, dy);
    const influence = cursor ? Math.max(0, 1 - distance / radius) * strength : 0;
    const wave = .72 + .28 * Math.cos(distance / 11 - tile.phase * 2);
    const alpha = tile.opacity * .52 + influence * .40 * wave;
    if (alpha < .012) continue;
    ctx.globalAlpha = Math.min(.92, alpha);
    const x = tile.x + dx * influence * .14;
    const y = tile.y + dy * influence * .14;
    const size = tile.size + influence * 5;
    ctx.fillRect(x - size / 2, y - size / 2, size, size);
  }
  ctx.globalAlpha = 1;
}

function tick(): void {
  animation = 0;
  if (gate.hidden) return;
  if (target) {
    cursor ??= { ...target };
    cursor.x += (target.x - cursor.x) * .18;
    cursor.y += (target.y - cursor.y) * .18;
  }
  const goal = target ? 1 : 0;
  strength += (goal - strength) * .18;
  if (Math.abs(goal - strength) < .005) strength = goal;
  draw();
  if (goal !== strength || (cursor && target && Math.hypot(cursor.x - target.x, cursor.y - target.y) > .25)) {
    schedule();
  }
}

function schedule(): void {
  if (!animation) animation = requestAnimationFrame(tick);
}

function resize(): void {
  width = gate.clientWidth;
  height = gate.clientHeight;
  if (!width || !height || !ctx) return;
  const ratio = Math.min(devicePixelRatio || 1, 2);
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  arrange();
  draw();
}

new ResizeObserver(resize).observe(gate);

gate.addEventListener('pointermove', (event) => {
  if (event.pointerType !== 'mouse' || !finePointer.matches || reduce.matches || width <= 760) return;
  const bounds = gate.getBoundingClientRect();
  target = { x: event.clientX - bounds.left, y: event.clientY - bounds.top };
  schedule();
}, { passive: true });
gate.addEventListener('pointerleave', () => {
  target = null;
  if (strength) schedule();
});
reduce.addEventListener('change', () => {
  target = cursor = null;
  strength = 0;
  draw();
});

const deck = requireElement<HTMLElement>('.index-deck');
const sheets = [...deck.querySelectorAll<HTMLButtonElement>('[data-sheet-tone]')];
const lookup = requireElement<HTMLElement>('.index-lookup');
const lookupLabel = requireElement<HTMLElement>('.lookup-query span');
const lookupIcon = requireElement<HTMLImageElement>('.lookup-source img');
const snippet = requireElement<HTMLElement>('.lookup-snippet');
let selectedSheet = requireElement<HTMLButtonElement>('.sheet-front');
let previewedSheet = selectedSheet;
let lookupAnimation: Animation | undefined;

function previewSheet(sheet: HTMLButtonElement): void {
  if (sheet === previewedSheet) return;
  previewedSheet = sheet;
  for (const item of sheets) item.classList.toggle('is-preview', sheet === item);
  lookup.dataset.sheetTone = sheet.dataset.sheetTone ?? 'policy';
  lookupLabel.textContent = sheet.querySelector('strong')?.textContent ?? '';
  const icon = sheet.querySelector('img');
  if (icon) lookupIcon.src = icon.src;
  lookupAnimation?.cancel();
  if (!reduce.matches) {
    lookupAnimation = snippet.animate([{ opacity: .48, translate: '-4px 0' }, { opacity: 1, translate: '0 0' }], {
      duration: 260,
      easing: 'ease-out',
    });
  }
}

for (const sheet of sheets) {
  sheet.addEventListener('pointerenter', (event) => {
    if (event.pointerType === 'mouse') previewSheet(sheet);
  });
  sheet.addEventListener('focus', () => previewSheet(sheet));
  sheet.addEventListener('click', () => {
    selectedSheet = sheet;
    for (const item of sheets) item.setAttribute('aria-pressed', String(sheet === item));
    previewSheet(sheet);
  });
}

deck.addEventListener('pointerleave', () => previewSheet(selectedSheet));
deck.addEventListener('focusout', (event) => {
  if (!(event.relatedTarget instanceof Node) || !deck.contains(event.relatedTarget)) previewSheet(selectedSheet);
});

function enableTilt(zone: HTMLElement, card: HTMLElement, maxX: number, maxY: number): void {
  function resetTilt(): void {
    card.classList.remove('is-tilting');
    card.style.removeProperty('--tilt-x');
    card.style.removeProperty('--tilt-y');
  }

  zone.addEventListener('pointermove', (event) => {
    if (event.pointerType !== 'mouse' || !finePointer.matches || reduce.matches || width <= 760) return;
    const bounds = zone.getBoundingClientRect();
    const x = Math.max(-1, Math.min(1, ((event.clientX - bounds.left) / bounds.width) * 2 - 1));
    const y = Math.max(-1, Math.min(1, ((event.clientY - bounds.top) / bounds.height) * 2 - 1));
    card.classList.add('is-tilting');
    card.style.setProperty('--tilt-x', `${(-y * maxX).toFixed(2)}deg`);
    card.style.setProperty('--tilt-y', `${(x * maxY).toFixed(2)}deg`);
  }, { passive: true });
  zone.addEventListener('pointerleave', resetTilt);
  zone.addEventListener('pointercancel', resetTilt);
  window.addEventListener('blur', resetTilt);
  reduce.addEventListener('change', resetTilt);
}

enableTilt(requireElement('.demo-illustration'), requireElement('.art-index'), 5, 7);
for (const zone of gate.querySelectorAll<HTMLElement>('.campus-topics li')) {
  const card = zone.querySelector<HTMLElement>('.campus-topic-card');
  if (card) enableTilt(zone, card, 7, 10);
}

const ripplePlane = requireElement<HTMLElement>('.ripple-plane');
gate.addEventListener('pointerdown', (event) => {
  if (!event.isPrimary || event.button !== 0 || reduce.matches) return;
  if (event.target instanceof Element && event.target.closest('input, label')) return;
  const bounds = ripplePlane.getBoundingClientRect();
  const ring = document.createElement('span');
  ring.className = 'click-ripple';
  ring.style.left = `${event.clientX - bounds.left}px`;
  ring.style.top = `${event.clientY - bounds.top}px`;
  if (ripplePlane.childElementCount >= 6) ripplePlane.firstElementChild?.remove();
  ripplePlane.append(ring);
  ring.addEventListener('animationend', () => ring.remove(), { once: true });
  ring.addEventListener('animationcancel', () => ring.remove(), { once: true });
}, { passive: true });
