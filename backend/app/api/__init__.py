"""API routers."""

from backend.app.api import actions, assistant, security, auth, clinical, command, data_platform, jobs, operations, reception, system, users

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
    command.router,
    assistant.router,
    data_platform.router,
    actions.router,
    security.router,
    security.knowledge_router,
    users.router,
]
