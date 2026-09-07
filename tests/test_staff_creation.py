import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status

from audit.models import AuditLog

User = get_user_model()


@pytest.fixture
def hospital_admin_user(db, hospital_a):
    return User.objects.create_user(
        username="hosp_admin",
        password="TestPassword123!",
        role="hospital_admin",
        hospital=hospital_a,
        first_name="Hosp",
        last_name="Admin",
        email="hosp_admin@test.local",
    )


@pytest.fixture
def hospital_admin_without_hospital(db):
    return User.objects.create_user(
        username="hosp_admin_no_hosp",
        password="TestPassword123!",
        role="hospital_admin",
        hospital=None,
        first_name="NoHosp",
        last_name="Admin",
        email="nohosp_admin@test.local",
    )


@pytest.fixture
def super_admin_user(db):
    return User.objects.create_user(
        username="super_admin",
        password="TestPassword123!",
        role="super_admin",
        first_name="Super",
        last_name="Admin",
        email="super_admin@test.local",
    )


@pytest.fixture
def django_superuser(db):
    return User.objects.create_superuser(
        username="django_super",
        password="TestPassword123!",
        email="django_super@test.local",
    )


@pytest.mark.django_db
def test_super_admin_creates_user(client, super_admin_user, hospital_a):
    client.force_login(super_admin_user)
    payload = {
        "username": "new_doc_1",
        "first_name": "New",
        "last_name": "Doc",
        "email": "new_doc_1@test.local",
        "role": "doctor",
        "hospital_id": hospital_a.id,
        "password": "Password123456!",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["username"] == "new_doc_1"
    assert response.data["hospital"]["id"] == hospital_a.id


@pytest.mark.django_db
def test_hospital_admin_creates_user(client, hospital_admin_user, hospital_a):
    client.force_login(hospital_admin_user)
    payload = {
        "username": "new_nurse_1",
        "first_name": "New",
        "last_name": "Nurse",
        "email": "new_nurse_1@test.local",
        "role": "nurse",
        "password": "Password123456!",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["username"] == "new_nurse_1"
    assert response.data["hospital"]["id"] == hospital_a.id


@pytest.mark.django_db
def test_django_superuser_creates_user(client, django_superuser, hospital_a):
    client.force_login(django_superuser)
    payload = {
        "username": "new_doc_2",
        "first_name": "New",
        "last_name": "Doc2",
        "email": "new_doc_2@test.local",
        "role": "doctor",
        "hospital_id": hospital_a.id,
        "password": "Password123456!",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
def test_hospital_admin_cannot_create_super_admin(client, hospital_admin_user):
    client.force_login(hospital_admin_user)
    payload = {
        "username": "illegal_super",
        "first_name": "Illegal",
        "last_name": "Super",
        "email": "illegal_super@test.local",
        "role": "super_admin",
        "password": "Password123456!",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "cannot assign the super_admin role" in response.data["error"]


@pytest.mark.django_db
def test_hospital_admin_without_hospital_rejected(client, hospital_admin_without_hospital):
    client.force_login(hospital_admin_without_hospital)
    payload = {
        "username": "orphan_staff",
        "first_name": "Orphan",
        "last_name": "Staff",
        "email": "orphan_staff@test.local",
        "role": "doctor",
        "password": "Password123456!",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "not assigned to a hospital" in response.data["error"]


@pytest.mark.django_db
@override_settings(
    AUTH_PASSWORD_VALIDATORS=[
        {
            "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
            "OPTIONS": {"min_length": 12},
        }
    ]
)
def test_short_password_rejected(client, super_admin_user, hospital_a):
    client.force_login(super_admin_user)
    payload = {
        "username": "short_pwd_user",
        "first_name": "Short",
        "last_name": "Pwd",
        "email": "short_pwd_user@test.local",
        "role": "doctor",
        "hospital_id": hospital_a.id,
        "password": "short",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "at least 12 characters" in response.data["error"]


@pytest.mark.django_db
def test_duplicate_username_returns_serializer_error(client, super_admin_user, hospital_a):
    client.force_login(super_admin_user)
    payload = {
        "username": super_admin_user.username,
        "first_name": "Dup",
        "last_name": "User",
        "email": "dup@test.local",
        "role": "doctor",
        "hospital_id": hospital_a.id,
        "password": "Password123456!",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "username" in response.data


@pytest.mark.django_db
def test_staff_creation_creates_audit_log(client, super_admin_user, hospital_a):
    client.force_login(super_admin_user)
    payload = {
        "username": "audit_doc_1",
        "first_name": "Audit",
        "last_name": "Doc",
        "email": "audit_doc_1@test.local",
        "role": "doctor",
        "hospital_id": hospital_a.id,
        "password": "Password123456!",
    }
    response = client.post("/api/staff/", payload, content_type="application/json")
    assert response.status_code == status.HTTP_201_CREATED

    log = AuditLog.objects.filter(
        action="STAFF_CREATED", target_id=str(response.data["id"])
    ).first()
    assert log is not None
    assert log.extra.get("target_user") == "audit_doc_1"
    assert log.extra.get("role") == "doctor"


@pytest.mark.django_db
def test_staff_detail_patch_ignores_password(client, hospital_admin_user, hospital_a):
    client.force_login(hospital_admin_user)
    colleague = User.objects.create_user(
        username="colleague_1",
        password="InitialPassword123!",
        role="doctor",
        hospital=hospital_a,
    )
    patch_payload = {
        "password": "HackedPassword123!",
        "first_name": "UpdatedName",
    }
    response = client.patch(
        f"/api/staff/{colleague.pk}/",
        patch_payload,
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["first_name"] == "UpdatedName"
    assert "password" not in response.data

    # Verify password was NOT changed
    colleague.refresh_from_db()
    assert colleague.first_name == "UpdatedName"
    assert colleague.check_password("InitialPassword123!") is True
    assert colleague.check_password("HackedPassword123!") is False


@pytest.mark.django_db
def test_staff_detail_patch_creates_audit_log(client, hospital_admin_user, hospital_a):
    client.force_login(hospital_admin_user)
    colleague = User.objects.create_user(
        username="colleague_2",
        password="InitialPassword123!",
        role="doctor",
        hospital=hospital_a,
    )
    patch_payload = {
        "bio": "Specialist in Cardiology",
        "phone": "+1234567890",
    }
    response = client.patch(
        f"/api/staff/{colleague.pk}/",
        patch_payload,
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_200_OK

    log = AuditLog.objects.filter(action="STAFF_UPDATED", target_id=str(colleague.pk)).first()
    assert log is not None
    assert log.extra.get("target_user") == "colleague_2"
    assert "bio" in log.extra.get("updated_fields", [])


@pytest.mark.django_db
def test_unassigned_hospital_admin_cannot_manage_super_admin(
    client, hospital_admin_without_hospital, super_admin_user
):
    client.force_login(hospital_admin_without_hospital)

    # 1. Detail GET must be 403 Forbidden
    resp = client.get(f"/api/staff/{super_admin_user.pk}/")
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 2. Detail PATCH must be 403 Forbidden
    resp = client.patch(
        f"/api/staff/{super_admin_user.pk}/",
        {"first_name": "Tampered"},
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 3. Set Active must be 403 Forbidden
    resp = client.post(
        f"/api/staff/{super_admin_user.pk}/set-active/",
        {"is_active": False},
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 4. Reset Password must be 403 Forbidden
    resp = client.post(
        f"/api/staff/{super_admin_user.pk}/reset-password/",
        {"password": "TakeoverPassword123!"},
        content_type="application/json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # 5. List staff should return empty list (no leakage of super_admins or orphaned users)
    resp = client.get("/api/staff/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["count"] == 0
