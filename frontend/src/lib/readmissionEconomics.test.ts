import { describe, expect, it } from "vitest";

import type { ReadmissionEconomics } from "../api/schemas/command";
import { programmeEconomics } from "./readmissionEconomics";

const facts: ReadmissionEconomics = {
  period_start: "2019-05-26",
  period_end: "2020-05-24",
  discharges: 1000,
  unplanned_readmissions: 100,
  readmission_rate_pct: 10,
  avg_cost_per_stay: 10_000,
  avg_los_days: 5,
  model_roc_auc: 0.8,
  model_flag_share_pct: 10,
  model_capture_pct: 40,
  model_precision_pct: 40,
  model_test_positives: 50,
  default_effectiveness_pct: 20,
  default_cost_per_enrolled: 150,
  notes: [],
};

describe("programmeEconomics", () => {
  it("targets the flagged share and reaches the captured readmissions", () => {
    const r = programmeEconomics(facts, { effectivenessPct: 25, costPerEnrolled: 200 }, true);
    expect(r.enrolled).toBe(100);
    expect(r.readmissionsReached).toBe(40);
    expect(r.prevented).toBe(10);
    expect(r.savings).toBe(100_000);
    expect(r.programmeCost).toBe(20_000);
    expect(r.net).toBe(80_000);
    expect(r.bedDaysFreed).toBe(50);
    expect(r.breakEvenCostPerEnrolled).toBe(1_000);
    expect(r.roiPct).toBe(400);
  });

  it("enrolling everyone reaches every readmission at full cost", () => {
    const r = programmeEconomics(facts, { effectivenessPct: 25, costPerEnrolled: 200 }, false);
    expect(r.enrolled).toBe(1000);
    expect(r.prevented).toBe(25);
    expect(r.net).toBe(250_000 - 200_000);
  });

  it("has no ROI when the programme is free", () => {
    expect(programmeEconomics(facts, { effectivenessPct: 10, costPerEnrolled: 0 }, true).roiPct).toBeNull();
  });
});
