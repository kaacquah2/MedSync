"""
Tests for inter-hospital access control.

Verifies:
  - can_access_patient() decision function (all four basis paths)
  - /api/patients/<nhid>/ gate: 403 without relationship, 200 with one
  - Break-glass via /api/patients/<nhid>/break-glass/: creates time-boxed grant
  - Break-glass expiry: expired grant → 403
  - Auto-creation of TreatmentRelationship on encounter creation
  - Audit logging of ACCESS_DENIED and BREAK_GLASS events
  - SYSTEM_ADMIN always allowed
"""

import json
from datetime import timedelta

from django.utils import timezone

# ── Helper ─────────────────────────────────────────────────────────────────


def _break_glass(
    client, nhid, reason="Patient presented as unconscious — emergency access required"
):
    return client.post(
        f"/api/patients/{nhid}/break-glass/",
        json.dumps({"reason": reason}),
        content_type="application/json",
    )


# ── can_access_patient() unit tests ───────────────────────────────────────


class TestCanAccessPatient:
    def test_unauthenticated_is_denied(self, db, patient_a):
        from django.contrib.auth.models import AnonymousUser

        from access.permissions import can_access_patient

        anon = AnonymousUser()
        decision = can_access_patient(anon, patient_a)
        assert not decision
        assert decision.basis == "denied"

    def test_admin_always_allowed(self, db, sys_admin, patient_a):
        from access.permissions import can_access_patient

        decision = can_access_patient(sys_admin, patient_a)
        assert decision
        assert decision.basis == "admin"

    def test_hospital_admin_same_hospital_allowed(self, db, hospital_admin_a, patient_a):
        from access.permissions import can_access_patient

        decision = can_access_patient(hospital_admin_a, patient_a)
        assert decision
        assert decision.basis == "admin"

    def test_hospital_admin_cross_hospital_denied(self, db, hospital_admin_b, patient_a):
        from access.permissions import can_access_patient

        decision = can_access_patient(hospital_admin_b, patient_a)
        assert not decision
        assert decision.basis == "denied"

    def test_same_hospital_allowed(self, db, doctor_a, patient_a):
        from access.permissions import can_access_patient

        decision = can_access_patient(doctor_a, patient_a)
        assert decision
        assert decision.basis == "same_hospital"

    def test_cross_hospital_denied_without_relationship(self, db, doctor_b, patient_a):
        from access.permissions import can_access_patient

        decision = can_access_patient(doctor_b, patient_a)
        assert not decision
        assert decision.basis == "denied"

    def test_treatment_relationship_grants_access(self, db, doctor_b, patient_a, hospital_b):
        from access.models import TreatmentRelationship
        from access.permissions import can_access_patient

        TreatmentRelationship.objects.create(
            clinician=doctor_b,
            patient=patient_a,
            hospital=hospital_b,
        )
        decision = can_access_patient(doctor_b, patient_a)
        assert decision
        assert decision.basis == "treatment_relationship"

    def test_expired_treatment_relationship_is_denied(self, db, doctor_b, patient_a, hospital_b):
        from access.models import TreatmentRelationship
        from access.permissions import can_access_patient

        TreatmentRelationship.objects.create(
            clinician=doctor_b,
            patient=patient_a,
            hospital=hospital_b,
            ended_at=timezone.now() - timedelta(hours=1),
        )
        decision = can_access_patient(doctor_b, patient_a)
        assert not decision

    def test_break_glass_grants_access(self, db, doctor_b, patient_a):
        from access.models import BreakGlassAccess
        from access.permissions import can_access_patient

        BreakGlassAccess.objects.create(
            actor=doctor_b,
            patient=patient_a,
            reason="Emergency — patient collapsed",
            created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        decision = can_access_patient(doctor_b, patient_a)
        assert decision
        assert decision.basis == "break_glass"

    def test_expired_break_glass_is_denied(self, db, doctor_b, patient_a):
        from access.models import BreakGlassAccess
        from access.permissions import can_access_patient

        BreakGlassAccess.objects.create(
            actor=doctor_b,
            patient=patient_a,
            reason="Emergency — patient collapsed",
            created_at=timezone.now() - timedelta(hours=2),
            expires_at=timezone.now() - timedelta(hours=1),
        )
        decision = can_access_patient(doctor_b, patient_a)
        assert not decision
        assert decision.basis == "denied"


# ── /api/patients/<nhid>/ gate ─────────────────────────────────────────────


class TestPatientDetailGate:
    def test_cross_hospital_denied_without_relationship(self, client_as_doctor_b, patient_a):
        resp = client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 403

    def test_same_hospital_allowed(self, client_as_doctor_a, patient_a):
        resp = client_as_doctor_a.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_sysadmin_allowed_everywhere(self, client_as_sysadmin, patient_a):
        resp = client_as_sysadmin.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_hospital_admin_same_hospital_allowed(self, client_as_hospital_admin_a, patient_a):
        resp = client_as_hospital_admin_a.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_hospital_admin_cross_hospital_denied(self, client_as_hospital_admin_b, patient_a):
        resp = client_as_hospital_admin_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 403

    def test_cross_hospital_with_treatment_rel_allowed(
        self, client_as_doctor_b, doctor_b, patient_a, hospital_b
    ):
        from access.models import TreatmentRelationship

        TreatmentRelationship.objects.create(
            clinician=doctor_b,
            patient=patient_a,
            hospital=hospital_b,
            reason="Referral",
        )
        resp = client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_denied_access_is_audited(self, client_as_doctor_b, patient_a):
        from audit.models import AuditLog

        initial_count = AuditLog.objects.filter(action="ACCESS_DENIED").count()
        client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert AuditLog.objects.filter(action="ACCESS_DENIED").count() == initial_count + 1


# ── Break-glass ────────────────────────────────────────────────────────────


class TestBreakGlassRequest:
    def setup_method(self):
        from api.permissions import BreakGlassThrottle

        BreakGlassThrottle().cache.clear()

    def test_valid_submission_creates_grant(self, client_as_doctor_b, doctor_b, patient_a):
        from access.models import BreakGlassAccess

        resp = _break_glass(client_as_doctor_b, patient_a.universal_id)
        assert resp.status_code == 201
        grants = BreakGlassAccess.objects.filter(actor=doctor_b, patient=patient_a)
        assert grants.count() == 1
        assert grants.first().is_active
        assert grants.first().expires_at > timezone.now()

    def test_break_glass_grant_allows_subsequent_access(self, client_as_doctor_b, patient_a):
        _break_glass(client_as_doctor_b, patient_a.universal_id)
        resp = client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 200

    def test_break_glass_is_audited(self, client_as_doctor_b, patient_a):
        from audit.models import AuditLog

        _break_glass(client_as_doctor_b, patient_a.universal_id)
        assert (
            AuditLog.objects.filter(
                action="BREAK_GLASS",
                patient_nhid=patient_a.universal_id,
            ).count()
            == 1
        )

    def test_empty_reason_is_rejected(self, client_as_doctor_b, patient_a):
        resp = _break_glass(client_as_doctor_b, patient_a.universal_id, reason="")
        assert resp.status_code == 400

    def test_short_reason_is_rejected(self, client_as_doctor_b, patient_a):
        resp = _break_glass(client_as_doctor_b, patient_a.universal_id, reason="too short")
        assert resp.status_code == 400

    def test_expired_break_glass_denies_access(self, client_as_doctor_b, doctor_b, patient_a):
        from access.models import BreakGlassAccess

        BreakGlassAccess.objects.create(
            actor=doctor_b,
            patient=patient_a,
            reason="Old emergency — now expired",
            created_at=timezone.now() - timedelta(hours=2),
            expires_at=timezone.now() - timedelta(hours=1),
        )
        resp = client_as_doctor_b.get(f"/api/patients/{patient_a.universal_id}/")
        assert resp.status_code == 403

    def test_break_glass_throttling(self, client_as_doctor_b, patient_a):
        """Break-glass endpoint must enforce BreakGlassThrottle (rate limited to 5/hour)."""
        from api.permissions import BreakGlassThrottle

        BreakGlassThrottle().cache.clear()

        for i in range(5):
            res = _break_glass(
                client_as_doctor_b,
                patient_a.universal_id,
                reason=f"Emergency reason #{i} for break glass",
            )
            assert res.status_code in (200, 201)

        # 6th attempt must be throttled with HTTP 429
        throttled_res = _break_glass(
            client_as_doctor_b, patient_a.universal_id, reason="Emergency reason #6 for break glass"
        )
        assert throttled_res.status_code == 429


# ── TreatmentRelationship auto-creation ───────────────────────────────────


class TestAutoTreatmentRelationship:
    def test_encounter_create_opens_treatment_relationship(
        self, client_as_doctor_b, doctor_b, patient_b, hospital_b
    ):
        from access.models import TreatmentRelationship

        assert not TreatmentRelationship.objects.filter(
            clinician=doctor_b, patient=patient_b
        ).exists()

        client_as_doctor_b.post(
            f"/api/patients/{patient_b.universal_id}/encounters/",
            json.dumps({"encounter_type": "OPD", "chief_complaint": "Routine check-up"}),
            content_type="application/json",
        )

        assert TreatmentRelationship.objects.filter(clinician=doctor_b, patient=patient_b).exists()

    def test_encounter_create_is_idempotent_for_relationship(
        self, client_as_doctor_b, doctor_b, patient_b, hospital_b
    ):
        from access.models import TreatmentRelationship

        for _ in range(2):
            client_as_doctor_b.post(
                f"/api/patients/{patient_b.universal_id}/encounters/",
                json.dumps({"encounter_type": "OPD", "chief_complaint": "Follow-up visit"}),
                content_type="application/json",
            )
        assert (
            TreatmentRelationship.objects.filter(clinician=doctor_b, patient=patient_b).count() == 1
        )


# ── ensure_treatment_relationship utility ─────────────────────────────────


class TestEnsureTreatmentRelationship:
    def test_creates_relationship_when_absent(self, db, doctor_b, patient_a, hospital_b):
        from access.models import TreatmentRelationship
        from access.permissions import ensure_treatment_relationship

        result = ensure_treatment_relationship(doctor_b, patient_a, hospital_b)
        assert result is not None
        assert (
            TreatmentRelationship.objects.filter(clinician=doctor_b, patient=patient_a).count() == 1
        )

    def test_does_not_duplicate_when_present(self, db, doctor_b, patient_a, hospital_b):
        from access.models import TreatmentRelationship
        from access.permissions import ensure_treatment_relationship

        ensure_treatment_relationship(doctor_b, patient_a, hospital_b)
        result = ensure_treatment_relationship(doctor_b, patient_a, hospital_b)
        assert result is None
        assert (
            TreatmentRelationship.objects.filter(clinician=doctor_b, patient=patient_a).count() == 1
        )


class TestPatientConsentApi:
    def test_grant_and_revoke_consent_via_api(self, client_as_doctor_b, doctor_b, patient_a, hospital_b):
        from access.models import PatientConsent

        # 1. Grant consent
        res = client_as_doctor_b.post(
            "/api/consents/",
            json.dumps({"patient": patient_a.universal_id, "hospital": hospital_b.pk, "notes": "Consent for specialist"}),
            content_type="application/json",
        )
        assert res.status_code in (200, 201)
        consent_id = res.json()["id"]

        # Verify can_access_patient now allows cross-hospital doctor_b
        from access.permissions import can_access_patient
        decision = can_access_patient(doctor_b, patient_a)
        assert decision
        assert decision.basis == "patient_consent"

        # 2. List consents
        res_list = client_as_doctor_b.get(f"/api/consents/?patient={patient_a.universal_id}")
        assert res_list.status_code == 200
        assert len(res_list.json()) >= 1

        # 3. Revoke consent via PATCH
        res_patch = client_as_doctor_b.patch(
            f"/api/consents/{consent_id}/",
            json.dumps({"granted": False}),
            content_type="application/json",
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["granted"] is False

        # Verify can_access_patient now denies doctor_b
        decision_revoked = can_access_patient(doctor_b, patient_a)
        assert not decision_revoked


class TestReferralAcceptanceTreatmentRelationship:
    def test_accepted_referral_creates_treatment_relationship(
        self, client_as_doctor_b, doctor_b, patient_a, hospital_a, hospital_b, doctor_a
    ):
        from access.models import TreatmentRelationship
        from referrals.models import Referral

        ref = Referral.objects.create(
            patient=patient_a,
            from_hospital=hospital_a,
            to_hospital=hospital_b,
            from_provider=doctor_a,
            reason="Cardiology evaluation",
        )

        res = client_as_doctor_b.patch(
            f"/api/referrals/{ref.pk}/status/",
            json.dumps({"status": "accepted", "status_notes": "Accepted for OPD"}),
            content_type="application/json",
        )
        assert res.status_code == 200
        assert TreatmentRelationship.objects.filter(clinician=doctor_b, patient=patient_a).exists()


class TestBreakGlassSetNull:
    def test_deleting_actor_preserves_break_glass_access(self, db, doctor_b, patient_a):
        from access.models import BreakGlassAccess

        bg = BreakGlassAccess.objects.create(
            actor=doctor_b,
            patient=patient_a,
            reason="Emergency access",
            created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )
        doctor_b_pk = doctor_b.pk
        doctor_b.delete()

        bg.refresh_from_db()
        assert bg.actor is None
        assert bg.patient == patient_a

    def test_deleting_patient_protected_when_break_glass_exists(self, db, doctor_b, patient_a):
        import pytest
        from django.db.models import ProtectedError
        from access.models import BreakGlassAccess

        BreakGlassAccess.objects.create(
            actor=doctor_b,
            patient=patient_a,
            reason="Emergency access protection test",
            created_at=timezone.now(),
            expires_at=timezone.now() + timedelta(hours=1),
        )

        with pytest.raises(ProtectedError):
            patient_a.delete()

