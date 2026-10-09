"""API routers. Each page migration adds its router here."""

from backend.app.api import auth, jobs, reception, system

routers = [auth.router, system.router, jobs.router, reception.router]
