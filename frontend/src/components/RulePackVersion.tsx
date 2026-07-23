// WS1.E3 — tenant-visible rule-pack version line (Shell footnote). The version shown is only
// ever what Mahsa REPORTS it loaded (GET /api/health/rulepack passes Mahsa's /health through);
// when it is unknown (sidecar down, request failed) the line renders nothing rather than a
// stale or assumed value — same honesty rule as VerifiedNumber. Changelog: dif/rules/CHANGELOG.md.
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export type RulePack = {
  version: string | null;
  channel: string | null;
};

export function RulePackVersion() {
  const { data } = useQuery({
    queryKey: ["health", "rulepack"],
    queryFn: () => api<RulePack>("/health/rulepack"),
    staleTime: 5 * 60 * 1000, // packs change on notification days, not per click
  });
  if (!data?.version) return null; // unknown => say nothing, never guess
  return (
    <div style={{ marginTop: 10 }} title="Statutory rule-pack version the engine validated against">
      Rule pack {data.version}
      {data.channel && data.channel !== "stable" ? ` (${data.channel})` : ""}
    </div>
  );
}
