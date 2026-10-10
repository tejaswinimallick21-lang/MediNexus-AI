"""
Reception: service unit tests, parity with the analytics module, and endpoint contracts.
"""

import pytest

from backend.app.core.pagination import PageParams
from backend.app.schemas.reception import AppointmentRow, ReceptionFilters, ReceptionKpis, StatusDistribution, WaitInsights
from backend.app.services import reception as svc
from backend.tests.conftest import assert_contract, assert_error
from src.analytics.metrics import compute_reception_kpis


# ---- parity with src.analytics.metrics ---------------------------------------------------------

def test_kpis_match_analytics_metrics():
    legacy = compute_reception_kpis()
    new = svc.get_kpis().model_dump()
    for key, value in legacy.items():
        assert new[key] == pytest.approx(value), key


def test_status_distribution_sums_to_total():
    dist = svc.get_status_distribution()
    assert sum(i.count for i in dist.items) == svc.get_kpis().total_appointments


# ---- service behaviour ----------------------------------------------------------------------

def test_appointments_expose_no_identifiers_or_clinical_reasons():
    page = svc.list_appointments(PageParams(limit=50))
    assert not {"reason_for_visit", "patient_name", "contact"} & set(AppointmentRow.model_fields)
    assert all(r.visit_type in {"Wellness visit", "Ambulatory visit", "Outpatient visit"} for r in page.items)


def test_appointments_filter_and_paginate():
    first = svc.list_appointments(PageParams(limit=10), status="No-Show")
    assert len(first.items) == 10 and all(r.status == "No-Show" for r in first.items)
    assert first.next_cursor is not None
    second = svc.list_appointments(PageParams(limit=10, offset=10), status="No-Show")
    assert not {r.appointment_id for r in first.items} & {r.appointment_id for r in second.items}


def test_wait_insights_are_computed_and_flagged_simulated():
    insights = svc.get_wait_insights()
    assert insights.wait_times_simulated is True
    assert insights.by_hour and len(insights.findings) == 3


# ---- endpoint contracts ---------------------------------------------------------------------

def test_kpis_contract(login):
    assert_contract(login("analyst").get("/api/reception/kpis"), ReceptionKpis, "reception_kpis")


def test_status_distribution_contract(login):
    assert_contract(login("analyst").get("/api/reception/status-distribution"), StatusDistribution, "reception_status_distribution")


def test_wait_insights_contract(login):
    assert_contract(login("analyst").get("/api/reception/wait-insights"), WaitInsights, "reception_wait_insights")


def test_filters_contract(login):
    assert_contract(login("analyst").get("/api/reception/filters"), ReceptionFilters, "reception_filters")


def test_appointments_contract(login):
    from backend.app.core.pagination import Page

    body = assert_contract(
        login("analyst").get("/api/reception/appointments", params={"limit": 5, "status": "Completed"}),
        Page[AppointmentRow],
        "reception_appointments",
    )
    assert len(body["items"]) == 5 and body["next_cursor"]


def test_appointments_limit_is_capped(login):
    assert_error(login("analyst").get("/api/reception/appointments", params={"limit": 500}), 422, "validation_error")


def test_bad_cursor(login):
    assert_error(login("analyst").get("/api/reception/appointments", params={"cursor": "@@"}), 400, "invalid_cursor")


@pytest.mark.parametrize("role", ["hcp"])
def test_other_roles_are_forbidden(login, role):
    assert_error(login(role).get("/api/reception/kpis"), 403, "forbidden")


def test_requires_sign_in(client):
    assert_error(client.get("/api/reception/kpis"), 401, "not_authenticated")
