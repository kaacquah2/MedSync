from django.urls import path

from . import views

# No app_name — included directly at /fhir/

urlpatterns = [
    # FHIR CapabilityStatement — no auth required; allows connecting systems to
    # discover supported resources and operations before authenticating.
    path(
        "metadata",
        views.capability_statement,
        name="fhir_metadata",
    ),
    path(
        "Patient/<str:universal_id>/",
        views.patient_resource,
        name="fhir_patient",
    ),
    path(
        "Patient/<str:universal_id>/$everything",
        views.patient_everything_endpoint,
        name="fhir_patient_everything",
    ),
]
