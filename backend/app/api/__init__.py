"""API routers."""

from backend.app.api import auth, clinical, jobs, operations, reception, system

routers = [
    auth.router,
    system.router,
    jobs.router,
    reception.router,
    operations.lab_router,
    operations.pharmacy_router,
    operations.executive_router,
    operations.agents_router,
    clinical.clinical_router,
    clinical.patients_router,
]
