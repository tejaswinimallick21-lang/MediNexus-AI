import { z } from "zod";

import { request } from "./client";
import {
  CareGapPageSchema,
  CareGapSummaryListSchema,
  ClinicalKpisSchema,
  EncounterListSchema,
  HuddleListSchema,
  LabPageSchema,
  LabSeriesSchema,
  MedicationPageSchema,
  Patient360Schema,
  PatientPageSchema,
  PatientRiskSchema,
} from "./schemas/clinical";

const enc = encodeURIComponent;
type PageQuery = { limit?: number; cursor?: string | null };

export const clinicalApi = {
  kpis: (s?: AbortSignal) => request("/clinical/kpis", ClinicalKpisSchema, { signal: s }),
  huddle: (limit: number, s?: AbortSignal) => request("/clinical/huddle", HuddleListSchema, { query: { limit }, signal: s }),
  careGapSummary: (s?: AbortSignal) => request("/clinical/care-gaps/summary", CareGapSummaryListSchema, { signal: s }),
  careGaps: (q: PageQuery & { gap?: string }, s?: AbortSignal) => request("/clinical/care-gaps", CareGapPageSchema, { query: q, signal: s }),
};

export const patientApi = {
  search: (q: PageQuery & { search?: string; tier?: string }, s?: AbortSignal) => request("/patients", PatientPageSchema, { query: q, signal: s }),
  get: (id: string, s?: AbortSignal) => request(`/patients/${enc(id)}`, Patient360Schema, { signal: s }),
  risk: (id: string, s?: AbortSignal) => request(`/patients/${enc(id)}/risk`, PatientRiskSchema, { signal: s }),
  labTests: (id: string, s?: AbortSignal) => request(`/patients/${enc(id)}/lab-tests`, z.array(z.string()), { signal: s }),
  labSeries: (id: string, test: string, s?: AbortSignal) => request(`/patients/${enc(id)}/labs/series`, LabSeriesSchema, { query: { test }, signal: s }),
  labs: (id: string, q: PageQuery, s?: AbortSignal) => request(`/patients/${enc(id)}/labs`, LabPageSchema, { query: q, signal: s }),
  medications: (id: string, q: PageQuery, s?: AbortSignal) => request(`/patients/${enc(id)}/medications`, MedicationPageSchema, { query: q, signal: s }),
  encounters: (id: string, s?: AbortSignal) => request(`/patients/${enc(id)}/encounters`, EncounterListSchema, { signal: s }),
};
