import type { ReadmissionEconomics } from "../api/schemas/command";

export interface ProgrammeInputs {
  effectivenessPct: number; // share of enrolled readmissions the programme prevents
  costPerEnrolled: number; // USD per enrolled patient
}

export interface ProgrammeResult {
  enrolled: number;
  readmissionsReached: number;
  prevented: number;
  savings: number;
  programmeCost: number;
  net: number;
  bedDaysFreed: number;
  breakEvenCostPerEnrolled: number;
  roiPct: number | null;
}

/**
 * Annual economics of a post-discharge programme (follow-up calls, early clinic visits).
 * targeted = enrol only the discharges the readmission model flags (held-out flag share / capture rate);
 * otherwise everyone discharged is enrolled and every readmission is reachable.
 */
export function programmeEconomics(facts: ReadmissionEconomics, inputs: ProgrammeInputs, targeted: boolean): ProgrammeResult {
  const enrolled = facts.discharges * (targeted ? facts.model_flag_share_pct / 100 : 1);
  const readmissionsReached = facts.unplanned_readmissions * (targeted ? facts.model_capture_pct / 100 : 1);
  const prevented = readmissionsReached * (inputs.effectivenessPct / 100);
  const savings = prevented * facts.avg_cost_per_stay;
  const programmeCost = enrolled * inputs.costPerEnrolled;
  return {
    enrolled,
    readmissionsReached,
    prevented,
    savings,
    programmeCost,
    net: savings - programmeCost,
    bedDaysFreed: prevented * facts.avg_los_days,
    breakEvenCostPerEnrolled: enrolled > 0 ? savings / enrolled : 0,
    roiPct: programmeCost > 0 ? ((savings - programmeCost) / programmeCost) * 100 : null,
  };
}
