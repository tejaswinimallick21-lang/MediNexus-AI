# MediNexus AI — Product Vision & Roadmap

**An operating system for multi-hospital networks** (e.g. a client like Apollo Hospitals): one trusted pipeline for patients, admissions, diagnoses, labs, pharmacy, equipment and billing, with role workspaces and AI agents that **propose and carry out actions**, not just report insights.

## Principles
1. **Decisions, not dashboards.** Every insight ends in a recommended action with an owner.
2. **Human-in-the-loop agents.** Agents propose; an authorized user approves; the platform executes and audits.
3. **Honest numbers.** Models are evaluated out-of-sample against baselines; simulated data is labelled; outcomes are never fabricated.
4. **Least data, right role.** Each role sees what it needs; admins oversee everything.

## Roles & workspaces
| Role | Workspace | Core jobs |
|---|---|---|
| **Admin** | Control Tower (+ every other workspace) | Pipeline & data quality, model registry & monitoring, agent governance (permissions, approval queue, action log), audit, infrastructure |
| **Analyst** | Command Center, Executive Operations, Patient Access | Readmission intelligence & cost, what-if simulator (doctor throughput, beds, staff, clinic hours), intervention ROI & risk-threshold planner, model performance & fairness, billing & revenue leakage |
| **HCP** | Care Console, Pharmacy, Laboratory | Patient 360 & risk timeline, morning huddle list, care-gap detection, follow-up agent, discharge planning, stockout prevention, critical-lab escalation |

## AI assistants (Claude API, tool use)
- **Nexa Care** (HCP): patient summaries, care gaps, drafts follow-ups / lab orders / patient messages for approval.
- **Nexa Insight** (Analyst): answers business questions over the lakehouse, runs what-if scenarios, explains model performance.
- **Nexa Ops** (Admin): pipeline status, data-quality issues, agent activity, policy questions.
- **RAG** over policies, clinical guidelines, model cards and the data dictionary, with citations.
- **Action loop:** propose → approve/reject → execute → audit (follow-ups, purchase orders, lab escalations, care-management enrolment).

## Signature features ("out of the box")
- **Readmission economics:** cost of every unplanned readmission, by condition, department and payer.
- **Threshold planner:** choose care-coordinator capacity → model shows readmissions prevented, cost, net savings (ties ML precision/recall to money).
- **Throughput what-if:** "+5 patients per doctor per day" → waiting time saved, backlog cleared, revenue, burnout risk flag.
- **Care-gap radar:** chronic patients overdue for tests or follow-ups.
- **Model health:** accuracy over time, drift, calibration, subgroup fairness.

## Data strategy
- **Clinical core:** Synthea (real simulated patient lifetimes; outcomes come from the simulation).
- **Operations simulator (generated, labelled `simulated`):** equipment assets & maintenance, staff rosters & clinician capacity, outpatient queues, care-management programmes, claims detail. Generators scale to any size for demos.
- **Never generated:** outcome labels (readmission, death, ICU) used to train or grade models.

## Roadmap
1. Finish all workspaces on the React platform; admin sees everything.
2. Analyst Command Center: readmission economics, what-if simulator, threshold planner, model monitor.
3. HCP Care Console: huddle list, care gaps, follow-up agent.
4. Nexa assistant page: RAG + tool-using agent + approval queue.
5. Operations simulator: equipment, staffing, care management; Admin Control Tower.
6. Retire Streamlit. ✅ (2026-10-10)
