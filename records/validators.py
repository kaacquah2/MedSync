"""
Input validation functions for clinical coding fields (ICD-10, SNOMED CT, LOINC, RxNorm).

Rejects malformed code formats at both model field validation and serializer validation layers.
"""

import re
from django.core.exceptions import ValidationError

# ICD-10-CM: Letter A-Z + 2 digits/chars + optional dot and 1-4 chars (e.g. J18.9, I10, E11.9, R51.9)
ICD10_REGEX = re.compile(r"^[A-Za-z][0-9][0-9A-Za-z](\.[0-9A-Za-z]{1,4})?$")

# SNOMED CT Concept ID: 6 to 18 digits (e.g. 233604007)
SNOMED_REGEX = re.compile(r"^[1-9][0-9]{5,17}$")

# LOINC code: 3 to 7 digits, hyphen, 1 check digit (e.g. 2947-0, 85354-9)
LOINC_REGEX = re.compile(r"^[0-9]{3,7}-[0-9]$")

# RxNorm CUI: 2 to 8 digits (e.g. 860975)
RXNORM_REGEX = re.compile(r"^[1-9][0-9]{1,7}$")


def validate_icd10(value):
    if value and not ICD10_REGEX.match(str(value).strip()):
        raise ValidationError(
            f"'{value}' is not a valid ICD-10 code format (expected e.g. 'J18.9', 'I10')."
        )


def validate_snomed(value):
    if value and not SNOMED_REGEX.match(str(value).strip()):
        raise ValidationError(
            f"'{value}' is not a valid SNOMED CT concept ID format (expected 6-18 digits)."
        )


def validate_loinc(value):
    if value and not LOINC_REGEX.match(str(value).strip()):
        raise ValidationError(
            f"'{value}' is not a valid LOINC code format (expected e.g. '2947-0')."
        )


def validate_rxnorm(value):
    if value and not RXNORM_REGEX.match(str(value).strip()):
        raise ValidationError(
            f"'{value}' is not a valid RxNorm CUI format (expected 2-8 digits)."
        )
