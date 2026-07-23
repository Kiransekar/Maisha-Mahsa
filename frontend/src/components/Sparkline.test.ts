// P2-3: honest ≥2-point rule for the SPA trend sparklines, mirroring app/web/charts.py's own
// test (test_history.py::test_sparkline_needs_two_points). renderToStaticMarkup — same pattern
// as VerifiedNumber.test.ts's LockChip test — no jsdom needed for a pure render.

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Sparkline } from "./Sparkline";

function render(values: number[]) {
  return renderToStaticMarkup(createElement(Sparkline, { values }));
}

describe("Sparkline — never draws a trend it doesn't have", () => {
  it("renders nothing for zero points", () => {
    expect(render([])).toBe("");
  });

  it("renders nothing for a single point — one point is not a trend", () => {
    expect(render([5])).toBe("");
  });

  it("renders a real polyline for two real points", () => {
    const html = render([1, 2]);
    expect(html).toContain("<svg");
    expect(html).toContain("<polyline");
  });

  it("renders a real polyline for three real points", () => {
    const html = render([1, 2, 3]);
    expect(html).toContain("<polyline");
    // 3 plotted points -> at least 3 coordinate pairs on the polyline.
    expect(html.match(/points="([^"]+)"/)?.[1].trim().split(" ").length).toBe(3);
  });

  it("MUTATION GUARD: the point count on the line always equals the real input length — a bug", () => {
    // that pads a lone real point into a fake two-point line would make this fail (2 real points
    // in -> exactly 2 plotted coordinates out, never 1 duplicated into 2, never a synthetic 3rd).
    const html = render([10, 20]);
    const points = html.match(/points="([^"]+)"/)?.[1].trim().split(" ") ?? [];
    expect(points).toHaveLength(2);
  });

  it("is safe when every value is identical (flat series, no divide-by-zero)", () => {
    const html = render([4, 4, 4]);
    expect(html).toContain("<polyline");
  });

  it("colors a rising series with the money-in hairline and a falling one with money-out", () => {
    expect(render([1, 2])).toContain("var(--color-money-in)");
    expect(render([2, 1])).toContain("var(--color-money-out)");
  });
});
