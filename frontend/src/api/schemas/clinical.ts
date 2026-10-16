import { z } from "zod";

import { pageOf } from "./common";

const str = z.string();
const optStr = z.string().nullable();
const num = z.number();
const optNum = z.number().nullable();

export const ClinicalKpisSchema = z.object({
  active_patients: num,
  in_treatment: num,
  awaiting_treatment: num,
  high_mortality_risk: num,
  open_care_gaps: num,
  data_through: str,
});

/** Tumour-board worklist: living cancer patients ranked by 12-month mortality risk. */
export const WorklistPatientSchema = z.object({
  patient_id: str,
  name: str,
  age: num,
  gender: str,
  cancer_type: str,
  cancer_stage: optStr,
  treatment_status: str,
  systemic_regimen: optStr,
  days_since_diagnosis: optNum,
  last_treatment_date: optStr,
  mortality_risk_pct: num,
  risk_level: str,
  drivers: z.array(str),
  tumor_marker: optStr,
  marker_value: optNum,
  marker_trend: optStr,
});
export type WorklistPatient = z.infer<typeof WorklistPatientSchema>;
export const WorklistSchema = z.array(WorklistPatientSchema);

export const CareGapSummaryListSchema = z.array(z.object({ gap: str, label: str, patients: num, guideline: str }));
export const CareGapSchema = z.object({ patient_id: str, name: str, age: num, gap: str, label: str, detail: str, last_done: optStr });
export type CareGap = z.infer<typeof CareGapSchema>;
export const CareGapPageSchema = pageOf(CareGapSchema);

export const PatientSummarySchema = z.object({
  patient_id: str,
  name: str,
  age: num,
  gender: str,
  cancer_type: optStr,
  cancer_stage: optStr,
  treatment_status: optStr,
  clinical_risk_tier: str,
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
  cancer_type: optStr,
  cancer_stage: optStr,
  diagnosis_date: optStr,
  age_at_diagnosis: optNum,
  treatment_status: optStr,
  systemic_regimen: optStr,
  surgery_procedure: optStr,
  surgery_date: optStr,
  first_treatment_date: optStr,
  days_to_treatment: optNum,
  chemo_cycles: num,
  immunotherapy_cycles: num,
  targeted_therapy_cycles: num,
  radiation_sessions: num,
  tumor_marker: optStr,
  marker_value: optNum,
  marker_flag: optStr,
  marker_trend: optStr,
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
  available: z.boolean(),
  scored_as_of: optStr,
  mortality_12m_pct: optNum,
  risk_level: optStr,
  cohort_rate_pct: optNum,
  method: optStr,
  drivers: z.array(str),
  survival_benchmark: z
    .object({ group: str, patients: num, one_year_pct: optNum, five_year_pct: optNum })
    .nullable(),
  care_plan: z.object({ pathway: str, primary_recommendation: str, checklist: z.array(str), rationale: z.array(str), disclaimer: str }),
  disclaimer: str,
});
export type PatientRisk = z.infer<typeof PatientRiskSchema>;

export const TreatmentEventSchema = z.object({
  event_date: str,
  event_type: str,
  detail: optStr,
  cycle: optNum,
  hospital_name: optStr,
});
export type TreatmentEvent = z.infer<typeof TreatmentEventSchema>;
export const TreatmentListSchema = z.array(TreatmentEventSchema);

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
  surgery_procedure: optStr,
  diagnoses: z.array(str),
});
export type Encounter = z.infer<typeof EncounterSchema>;
export const EncounterListSchema = z.array(EncounterSchema);
