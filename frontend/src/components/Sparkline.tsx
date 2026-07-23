// P2-3: inline-SVG sparklines for the SPA — mirrors app/web/charts.py's `sparkline()` geometry
// exactly (same pad/width/height, same "flat line when span is 0" fallback) so the two surfaces
// draw the identical shape from the identical points. No chart lib: a <polyline> is the whole
// budget. Fewer than 2 real points → renders NOTHING (never a fabricated flat line to fill the
// space) — that check lives here, once, so every caller gets it for free.

export function Sparkline({
  values,
  width = 96,
  height = 24,
  pad = 3,
}: {
  values: number[];
  width?: number;
  height?: number;
  pad?: number;
}) {
  if (values.length < 2) return null;

  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo;
  const n = values.length;
  const dx = (width - 2 * pad) / (n - 1);
  const y = (v: number) => (span === 0 ? height / 2 : pad + (height - 2 * pad) * (1 - (v - lo) / span));

  const pts = values.map((v, i) => `${(pad + i * dx).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const lastX = pad + (n - 1) * dx;
  const lastY = y(values[n - 1]);
  const rising = values[n - 1] >= values[0];
  const stroke = rising ? "var(--color-money-in)" : "var(--color-money-out)";

  return (
    <svg
      className="spark"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <polyline
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={pts}
      />
      <circle cx={lastX.toFixed(1)} cy={lastY.toFixed(1)} r={2} fill={stroke} />
    </svg>
  );
}
