"""Tiny, dependency-free inline-SVG sparklines (honoring the no-build-step constraint). Pure:
given a list of real values, return an SVG string. Fewer than 2 points → empty (we never draw
a trend we don't have)."""

from __future__ import annotations


def sparkline(values: list[float], *, width: int = 132, height: int = 32, pad: int = 3) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo
    n = len(values)
    dx = (width - 2 * pad) / (n - 1)

    def y(v: float) -> float:
        if span == 0:
            return height / 2  # flat line when every value is identical
        return pad + (height - 2 * pad) * (1 - (v - lo) / span)

    pts = " ".join(f"{pad + i * dx:.1f},{y(v):.1f}" for i, v in enumerate(values))
    last_x = pad + (n - 1) * dx
    last_y = y(values[-1])
    rising = values[-1] >= values[0]
    stroke = "var(--c-green)" if rising else "var(--c-red)"
    return (
        f'<svg class="spark" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" aria-hidden="true">'
        f'<polyline fill="none" stroke="{stroke}" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>'
        f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2" fill="{stroke}"/>'
        f"</svg>"
    )
