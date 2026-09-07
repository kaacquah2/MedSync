from unittest.mock import patch

import pytest
from django.test import override_settings
from rest_framework.exceptions import APIException, NotAuthenticated

from api.exceptions import emr_exception_handler


class TestEmrExceptionHandler:
    def test_not_authenticated_reclassified_to_401(self):
        exc = NotAuthenticated("Authentication credentials were not provided.")
        response = emr_exception_handler(exc, context={})
        assert response.status_code == 401
        assert response.data["status_code"] == 401
        assert "Authentication credentials were not provided" in response.data["error"]

    def test_api_exception_dict_detail(self):
        exc = APIException({"detail": "Custom API error"})
        response = emr_exception_handler(exc, context={})
        assert response.status_code == 500
        assert response.data == {
            "error": "Custom API error",
            "status_code": 500,
        }

    @override_settings(DEBUG=False)
    @patch("api.exceptions.logger")
    def test_unhandled_exception_logged_and_returns_500_when_debug_false(self, mock_logger):
        exc = RuntimeError("Database connection suddenly dropped")
        response = emr_exception_handler(exc, context={})
        mock_logger.exception.assert_called_once_with("Unhandled API exception", exc_info=exc)
        assert response.status_code == 500
        assert response.data == {
            "error": "An unexpected server error occurred.",
            "status_code": 500,
        }

    @override_settings(DEBUG=True)
    @patch("api.exceptions.logger")
    def test_unhandled_exception_raises_when_debug_true(self, mock_logger):
        exc = RuntimeError("Unexpected crash in debug mode")
        with pytest.raises(RuntimeError, match="Unexpected crash in debug mode"):
            emr_exception_handler(exc, context={})
        mock_logger.exception.assert_called_once_with("Unhandled API exception", exc_info=exc)
