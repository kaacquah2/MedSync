from unittest.mock import MagicMock

import pytest
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from api.idempotency import (
    check_idempotency,
    clear_idempotency,
    get_idempotency_key,
    store_idempotency,
)


@pytest.fixture(autouse=True)
def clear_test_cache():
    cache.clear()
    yield
    cache.clear()


class TestIdempotencyUnit:
    def test_no_header_returns_none(self):
        factory = APIRequestFactory()
        req = factory.post("/api/test/", data={"foo": "bar"}, format="json")
        req.user = MagicMock(is_authenticated=True, id=42)

        assert get_idempotency_key(req) is None
        resp, key = check_idempotency(req)
        assert resp is None
        assert key is None

    def test_key_includes_user_scope_header_and_body_hash(self):
        factory = APIRequestFactory()
        req = factory.post(
            "/api/test/",
            data={"foo": "bar"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="uuid-1234",
        )
        req.user = MagicMock(is_authenticated=True, id=99)

        key = get_idempotency_key(req, scope="test_scope")
        assert key is not None
        assert key.startswith("idempotency:key:99:test_scope:uuid-1234:")
        # Contains sha256 hex digest (64 chars) at the end
        parts = key.split(":")
        assert len(parts[-1]) == 64

    def test_anonymous_user_uses_anon(self):
        factory = APIRequestFactory()
        req = factory.post(
            "/api/test/",
            data={"foo": "bar"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="uuid-1234",
        )
        req.user = MagicMock(is_authenticated=False)

        key = get_idempotency_key(req, scope="test_scope")
        assert key.startswith("idempotency:key:anon:test_scope:uuid-1234:")

    def test_payload_canonicalisation_dict_key_order(self):
        factory = APIRequestFactory()
        req1 = factory.post(
            "/api/test/",
            data={"b": 2, "a": 1, "nested": {"z": 10, "y": 20}},
            format="json",
            HTTP_IDEMPOTENCY_KEY="uuid-order",
        )
        req2 = factory.post(
            "/api/test/",
            data={"a": 1, "nested": {"y": 20, "z": 10}, "b": 2},
            format="json",
            HTTP_IDEMPOTENCY_KEY="uuid-order",
        )
        req1.user = MagicMock(is_authenticated=True, id=1)
        req2.user = MagicMock(is_authenticated=True, id=1)

        key1 = get_idempotency_key(req1)
        key2 = get_idempotency_key(req2)
        assert key1 == key2

    def test_different_payloads_generate_different_keys(self):
        factory = APIRequestFactory()
        req1 = factory.post(
            "/api/test/",
            data={"drug": "Drug A"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="shared-uuid",
        )
        req2 = factory.post(
            "/api/test/",
            data={"drug": "Drug B"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="shared-uuid",
        )
        req1.user = MagicMock(is_authenticated=True, id=1)
        req2.user = MagicMock(is_authenticated=True, id=1)

        key1 = get_idempotency_key(req1)
        key2 = get_idempotency_key(req2)
        assert key1 != key2

    def test_reservation_and_in_flight_handling(self):
        factory = APIRequestFactory()
        req = factory.post(
            "/api/test/",
            data={"drug": "Amoxicillin"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="idem-inflight-test",
        )
        req.user = MagicMock(is_authenticated=True, id=10)

        # 1. First call reserves "in-flight"
        cached_resp, cache_key = check_idempotency(req)
        assert cached_resp is None
        assert cache_key is not None
        assert cache.get(cache_key) == "in-flight"

        # 2. Second concurrent call with same key and body gets 409 Conflict
        cached_resp_2, cache_key_2 = check_idempotency(req)
        assert cached_resp_2 is not None
        assert cached_resp_2.status_code == status.HTTP_409_CONFLICT
        assert "in progress" in cached_resp_2.data["detail"]
        assert cache_key_2 == cache_key

        # 3. Request finishes successfully with 201 Response
        success_resp = Response({"id": 123, "drug": "Amoxicillin"}, status=status.HTTP_201_CREATED)
        store_idempotency(cache_key, success_resp)

        # 4. Third call replaying the request gets the cached 201 Response
        cached_resp_3, cache_key_3 = check_idempotency(req)
        assert cached_resp_3 is not None
        assert cached_resp_3.status_code == status.HTTP_201_CREATED
        assert cached_resp_3.data == {"id": 123, "drug": "Amoxicillin"}

    def test_failure_releases_in_flight_reservation(self):
        factory = APIRequestFactory()
        req = factory.post(
            "/api/test/",
            data={"drug": "Amoxicillin"},
            format="json",
            HTTP_IDEMPOTENCY_KEY="idem-fail-test",
        )
        req.user = MagicMock(is_authenticated=True, id=10)

        cached_resp, cache_key = check_idempotency(req)
        assert cached_resp is None
        assert cache.get(cache_key) == "in-flight"

        # Store a 400 Bad Request or None to simulate failure
        fail_resp = Response({"error": "Validation failed"}, status=status.HTTP_400_BAD_REQUEST)
        store_idempotency(cache_key, fail_resp)

        # In-flight reservation should be released
        assert cache.get(cache_key) is None

        # Subsequent retry can acquire the reservation again
        cached_resp_retry, _ = check_idempotency(req)
        assert cached_resp_retry is None

    def test_clear_idempotency(self):
        cache.set("test-key", "in-flight")
        clear_idempotency("test-key")
        assert cache.get("test-key") is None
