import { useCallback, useMemo, useRef, useState } from 'react';

interface TagColorPickerProps {
  value: string;
  onChange: (hexColor: string) => void;
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function rgbToHex(r: number, g: number, b: number) {
  const toHex = (n: number) => clamp(Math.round(n), 0, 255).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

function hexToRgb(hex: string) {
  const normalized = hex.replace('#', '');
  const value = normalized.length === 3
    ? normalized.split('').map((char) => `${char}${char}`).join('')
    : normalized;

  const r = parseInt(value.slice(0, 2), 16);
  const g = parseInt(value.slice(2, 4), 16);
  const b = parseInt(value.slice(4, 6), 16);
  return {
    r: Number.isNaN(r) ? 0 : r,
    g: Number.isNaN(g) ? 0 : g,
    b: Number.isNaN(b) ? 0 : b,
  };
}

function rgbToHsv(r: number, g: number, b: number) {
  const rn = clamp(r, 0, 255) / 255;
  const gn = clamp(g, 0, 255) / 255;
  const bn = clamp(b, 0, 255) / 255;

  const max = Math.max(rn, gn, bn);
  const min = Math.min(rn, gn, bn);
  const delta = max - min;

  let h = 0;
  if (delta !== 0) {
    if (max === rn) h = ((gn - bn) / delta) % 6;
    else if (max === gn) h = (bn - rn) / delta + 2;
    else h = (rn - gn) / delta + 4;
  }

  const hue = Math.round((h * 60 + 360) % 360);
  const sat = max === 0 ? 0 : Math.round((delta / max) * 100);
  const val = Math.round(max * 100);

  return { h: hue, s: sat, v: val };
}

function hsvToRgb(h: number, s: number, v: number) {
  const hue = ((clamp(h, 0, 360) % 360) + 360) % 360;
  const sat = clamp(s, 0, 100) / 100;
  const val = clamp(v, 0, 100) / 100;

  const c = val * sat;
  const x = c * (1 - Math.abs((hue / 60) % 2 - 1));
  const m = val - c;

  let r = 0;
  let g = 0;
  let b = 0;

  if (hue < 60) [r, g, b] = [c, x, 0];
  else if (hue < 120) [r, g, b] = [x, c, 0];
  else if (hue < 180) [r, g, b] = [0, c, x];
  else if (hue < 240) [r, g, b] = [0, x, c];
  else if (hue < 300) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];

  return {
    r: Math.round((r + m) * 255),
    g: Math.round((g + m) * 255),
    b: Math.round((b + m) * 255),
  };
}

// ── Gradient Slider ──────────────────────────────────────────────────────────
interface GradientSliderProps {
  value: number;
  max: number;
  gradient: string;
  onChange: (v: number) => void;
  label: string;
}

function GradientSlider({ value, max, gradient, onChange, label }: GradientSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const pct = clamp((value / max) * 100, 0, 100);

  const getValueFromEvent = useCallback((clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return value;
    return Math.round(clamp((clientX - rect.left) / rect.width, 0, 1) * max);
  }, [max, value]);

  const onPointerDown = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    onChange(getValueFromEvent(e.clientX));
  }, [getValueFromEvent, onChange]);

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLDivElement>) => {
    if (e.buttons !== 1) return;
    onChange(getValueFromEvent(e.clientX));
  }, [getValueFromEvent, onChange]);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">{label}</span>
        <span className="text-[10px] font-medium text-foreground tabular-nums">{value}</span>
      </div>
      <div
        ref={trackRef}
        className="relative h-3 rounded-full cursor-pointer select-none"
        style={{ background: gradient }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
      >
        <div
          className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-4 h-4 rounded-full border-2 border-white shadow-md pointer-events-none"
          style={{ left: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function TagColorPicker({ value, onChange }: TagColorPickerProps) {
  const [hexInput, setHexInput] = useState('');
  const [editingHex, setEditingHex] = useState(false);
  const rgb = useMemo(() => hexToRgb(value), [value]);
  const hsv = useMemo(() => rgbToHsv(rgb.r, rgb.g, rgb.b), [rgb]);

  const hueGradient = 'linear-gradient(to right, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff, #ff00ff, #ff0000)';

  const satGradient = useMemo(() => {
    const { r: r0, g: g0, b: b0 } = hsvToRgb(hsv.h, 0, hsv.v);
    const { r: r1, g: g1, b: b1 } = hsvToRgb(hsv.h, 100, hsv.v);
    return `linear-gradient(to right, rgb(${r0},${g0},${b0}), rgb(${r1},${g1},${b1}))`;
  }, [hsv.h, hsv.v]);

  const valGradient = useMemo(() => {
    const { r, g, b } = hsvToRgb(hsv.h, hsv.s, 100);
    return `linear-gradient(to right, #000000, rgb(${r},${g},${b}))`;
  }, [hsv.h, hsv.s]);

  return (
    <div className="space-y-4">
      {/* Preview + hex */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-[6px] border border-border shrink-0" style={{ backgroundColor: value }} />
        <div className="flex-1">
          {editingHex ? (
            <input
              autoFocus
              value={hexInput}
              onChange={(e) => setHexInput(e.target.value)}
              onBlur={() => {
                const cleaned = hexInput.startsWith('#') ? hexInput : `#${hexInput}`;
                if (/^#[0-9a-fA-F]{6}$/.test(cleaned)) onChange(cleaned.toLowerCase());
                setEditingHex(false);
              }}
              onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }}
              className="w-full h-7 rounded-[3px] border border-border bg-surface-secondary px-2 text-[11px] font-mono"
              placeholder="#000000"
            />
          ) : (
            <button
              type="button"
              onClick={() => { setHexInput(value); setEditingHex(true); }}
              className="text-[12px] font-mono font-medium text-foreground hover:text-primary transition-colors"
            >
              {value.toUpperCase()}
            </button>
          )}
          <p className="text-[10px] text-muted-foreground mt-0.5">Clic para editar hex</p>
        </div>
      </div>

      {/* Gradient sliders */}
      <div className="space-y-3">
        <GradientSlider
          label="Tono"
          value={hsv.h}
          max={360}
          gradient={hueGradient}
          onChange={(h) => { const n = hsvToRgb(h, hsv.s, hsv.v); onChange(rgbToHex(n.r, n.g, n.b)); }}
        />
        <GradientSlider
          label="Saturación"
          value={hsv.s}
          max={100}
          gradient={satGradient}
          onChange={(s) => { const n = hsvToRgb(hsv.h, s, hsv.v); onChange(rgbToHex(n.r, n.g, n.b)); }}
        />
        <GradientSlider
          label="Brillo"
          value={hsv.v}
          max={100}
          gradient={valGradient}
          onChange={(v) => { const n = hsvToRgb(hsv.h, hsv.s, v); onChange(rgbToHex(n.r, n.g, n.b)); }}
        />
      </div>
    </div>
  );
}
