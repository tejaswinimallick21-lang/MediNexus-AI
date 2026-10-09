import { request } from "./client";
import {
  HospitalOptionListSchema,
  ModelMonitorListSchema,
  ReadmissionEconomicsSchema,
  WhatIfResultSchema,
  type WhatIfInput,
} from "./schemas/command";

export const commandApi = {
  hospitals: (s?: AbortSignal) => request("/command/hospitals", HospitalOptionListSchema, { signal: s }),
  whatIf: (body: WhatIfInput, s?: AbortSignal) => request("/command/what-if", WhatIfResultSchema, { method: "POST", body, signal: s }),
  readmissionEconomics: (s?: AbortSignal) => request("/command/readmission-economics", ReadmissionEconomicsSchema, { signal: s }),
  models: (s?: AbortSignal) => request("/command/models", ModelMonitorListSchema, { signal: s }),
};
