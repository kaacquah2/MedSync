import pytest
from patients.models import Patient, PatientSearchToken

@pytest.mark.django_db
class TestSearchTrigram:
    def test_search_partial_name(self, client_as_doctor_a, patient_a, hospital_a, doctor_a):
        # Create another patient
        patient_b = Patient.objects.create(
            first_name="Kofi",
            last_name="Mensah",
            date_of_birth="1990-01-01",
            sex="M",
            national_id="GHA-TEST-002",
            registered_at_hospital=hospital_a,
            registered_by=doctor_a,
        )

        # Check search tokens populated on save
        assert PatientSearchToken.objects.filter(patient=patient_a).exists()
        assert PatientSearchToken.objects.filter(patient=patient_b).exists()

        # Search for "yaw" (partial first name)
        resp = client_as_doctor_a.get("/api/patients/?q=yaw")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["first_name"] == "Yaw"

        # Search for "mens" (partial last name)
        resp = client_as_doctor_a.get("/api/patients/?q=mens")
        assert resp.status_code == 200
        results = resp.json()["results"]
        # Both "Yaw Mensah" and "Kofi Mensah" should be returned since both contain trigram "men", "ens"
        assert len(results) == 2
        names = {r["first_name"] for r in results}
        assert names == {"Yaw", "Kofi"}
        
        # Search for "kof" (partial first name)
        resp = client_as_doctor_a.get("/api/patients/?q=kof")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["first_name"] == "Kofi"
