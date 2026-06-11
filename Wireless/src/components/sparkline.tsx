/**
 * Tiny server-rendered SVG sparkline for 0-100 score history — no client JS.
 * Color follows the direction: green when the last point is at/above the
 * first (improving), red when it ends lower (degrading).
 */
export function Sparkline({
  points,
  width = 140,
  height = 36,
}: {
  points: number[];
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;
  // 2px padding keeps the stroke from clipping at the extremes.
  const pad = 2;
  const step = (width - pad * 2) / (points.length - 1);
  // y axis inverts (SVG origin is top-left); scores map 0-100 → bottom-top.
  const y = (v: number) => pad + (height - pad * 2) * (1 - v / 100);
  const coords = points.map((v, i) => `${pad + i * step},${y(v).toFixed(1)}`).join(" ");
  const improving = points[points.length - 1] >= points[0];
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="overflow-visible"
      role="img"
      aria-label={`Health trend from ${points[0]} to ${points[points.length - 1]}`}
    >
      <polyline
        points={coords}
        fill="none"
        stroke={improving ? "var(--good)" : "var(--critical)"}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Compact week-over-week delta chip: ▲ +4 (green) or ▼ −61 (red). */
export function DeltaChip({ delta }: { delta: number | null }) {
  if (delta === null) return <span className="text-xs text-muted">—</span>;
  if (delta === 0) return <span className="text-xs text-muted">±0</span>;
  const up = delta > 0;
  return (
    <span
      className={
        up
          ? "text-xs font-medium tabular-nums text-good"
          : "text-xs font-medium tabular-nums text-critical"
      }
    >
      {up ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  );
}
