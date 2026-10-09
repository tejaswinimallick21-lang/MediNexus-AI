import { z } from "zod";

import { pageOf } from "./common";

const str = z.string();
const optStr = z.string().nullable();
const num = z.number();

export const ClinicalKpisSchema = z.object({
  living_patients: num,
  high_tier_patients: num,
  recent_discharges: num,
  high_risk_recent_discharges: num,
  open_care_gaps: num,
  data_through: str,
});

export const HuddlePatientSchema = z.object({
  patient_id: str,
  name: str,
  age: num,
  gender: str,
  admission_id: str,
  discharge_date: str,
  admission_reason: optStr,
  department_name: optStr,
  readmission_probability_pct: num,
  risk_level: str,
  drivers: z.array(str),
  has_follow_up: z.boolean(),
});
export type HuddlePatient = z.infer<typeof HuddlePatientSchema>;
export const HuddleListSchema = z.array(HuddlePatientSchema);

export const CareGapSummaryListSchema = z.array(z.object({ gap: str, label: str, patients: num, guideline: str }));
export const CareGapSchema = z.object({ patient_id: str, name: str, age: num, gap: str, label: str, detail: str, last_done: optStr });
export type CareGap = z.infer<typeof CareGapSchema>;
export const CareGapPageSchema = pageOf(CareGapSchema);

export const PatientSummarySchema = z.object({
  patient_id: str,
  name: str,
  age: num,
  gender: str,
  clinical_risk_tier: str,
  total_admissions: num,
  is_deceased: z.boolean(),
});
export type PatientSummary = z.infer<typeof PatientSummarySchema>;
export const PatientPageSchema = pageOf(PatientSummarySchema);

export const Patient360Schema = z.object({
  patient_id: str,
  name: str,
  age: num,
  gender: str,
  blood_group: optStr,
  insurance_provider: optStr,
  city: optStr,
  is_deceased: z.boolean(),
  death_date: optStr,
  clinical_risk_tier: str,
  total_admissions: num,
  average_los_days: num,
  unplanned_readmissions: num,
  total_lab_tests: num,
  abnormal_lab_count: num,
  critical_lab_count: num,
  active_prescriptions: num,
  lifetime_billing: num,
  comorbidities: z.array(str),
  flags: z.record(z.boolean()),
  care_gaps: z.array(CareGapSchema),
});
export type Patient360 = z.infer<typeof Patient360Schema>;

export const PatientRiskSchema = z.object({
  covid_scored_as_of: optStr,
  covid_outcomes: z.array(
    z.object({ outcome: str, label: str, probability_pct: num, risk_level: str, cohort_rate_pct: num, observed: num.nullable() }),
  ),
  covid_drivers: z.array(str),
  readmission_available: z.boolean(),
  readmission_probability_pct: num.nullable(),
  readmission_risk_level: optStr,
  readmission_base_rate_pct: num.nullable(),
  readmission_drivers: z.array(str),
  readmission_admission_date: optStr,
  los_predicted_days: num.nullable(),
  los_observed_days: num.nullable(),
  los_interval: optStr,
  care_plan: z.object({ pathway: str, primary_recommendation: str, checklist: z.array(str), rationale: z.array(str), disclaimer: str }),
  disclaimer: str,
});
export type PatientRisk = z.infer<typeof PatientRiskSchema>;

export const LabSeriesSchema = z.object({
  test_name: str,
  unit: optStr,
  reference_range: optStr,
  points: z.array(z.object({ test_date: str, test_value: num.nullable(), abnormal_flag: str })),
});
export const LabResultSchema = z.object({
  test_date: str,
  test_name: str,
  test_value: num.nullable(),
  unit: optStr,
  reference_range: optStr,
  abnormal_flag: str,
});
export type LabResult = z.infer<typeof LabResultSchema>;
export const LabPageSchema = pageOf(LabResultSchema);

export const MedicationSchema = z.object({
  prescription_date: str,
  end_date: optStr,
  medication_name: optStr,
  category: optStr,
  dosage: optStr,
  status: str,
  indication: optStr,
});
export type Medication = z.infer<typeof MedicationSchema>;
export const MedicationPageSchema = pageOf(MedicationSchema);

export const EncounterSchema = z.object({
  admission_id: str,
  admission_date: str,
  discharge_date: str,
  length_of_stay_days: num.nullable(),
  admission_type: str,
  admission_reason: optStr,
  department_name: optStr,
  discharge_disposition: str,
  is_icu: z.boolean(),
  readmitted_30d: z.boolean(),
  diagnoses: z.array(str),
});
export type Encounter = z.infer<typeof EncounterSchema>;
export const EncounterListSchema = z.array(EncounterSchema);
