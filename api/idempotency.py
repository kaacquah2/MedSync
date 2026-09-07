"""
Idempotency and duplicate-submission protection for API endpoints.

Prevents double-click / duplicated submissions (e.g. prescription creation, lab orders)
when an `Idempotency-Key` HTTP header is supplied by caching responses for 300 seconds.
"""

import hashlib
import json

from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response


def get_request_body_hash(request):
    """
    Compute a SHA-256 hash of the canonicalised request payload.
    Ensures keys with different payloads do not collide or replay stale data.
    """
    data = None
    if hasattr(request, "data"):
        try:
            data = request.data
        except Exception:
            data = None

    if data is None:
        raw_body = getattr(request, "body", b"")
        if raw_body:
            try:
                if isinstance(raw_body, bytes):
                    data = json.loads(raw_body.decode("utf-8"))
                elif isinstance(raw_body, str):
                    data = json.loads(raw_body)
            except Exception:
                data = raw_body

    if data is not None:
        if isinstance(data, (dict, list)):
            canonical = json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))
        elif hasattr(data, "dict"):  # e.g. Django QueryDict
            canonical = json.dumps(data.dict(), sort_keys=True, default=str, separators=(",", ":"))
        elif isinstance(data, bytes):
            canonical = data.decode("utf-8", errors="replace")
        else:
            canonical = str(data)
    else:
        canonical = ""

    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_idempotency_key(request, scope=""):
    """
    Extract idempotency cache key if `Idempotency-Key` header is present.
    Hashes the canonicalised request payload into the key.
    Returns None if no idempotency header was provided.
    """
    key_header = request.headers.get("Idempotency-Key") or request.META.get("HTTP_IDEMPOTENCY_KEY")
    if not key_header:
        return None

    user_id = request.user.id if request.user and request.user.is_authenticated else "anon"
    body_hash = get_request_body_hash(request)
    return f"idempotency:key:{user_id}:{scope}:{key_header}:{body_hash}"


def check_idempotency(request, scope="", ttl=300):
    """
    Check if a request with an Idempotency-Key header is a duplicate submission.
    Atomically reserves the key using cache.add(cache_key, "in-flight").

    Returns (cached_response, cache_key):
    - (None, cache_key): Reservation acquired; caller may proceed with processing.
    - (Response(409), cache_key): Request is currently in flight by a concurrent worker.
    - (Response(cached), cache_key): Request was already completed; replaying cached response.
    - (None, None): No Idempotency-Key header provided.
    """
    cache_key = get_idempotency_key(request, scope=scope)
    if not cache_key:
        return None, None

    # Try to atomically reserve the key
    acquired = cache.add(cache_key, "in-flight", timeout=ttl)
    if acquired:
        return None, cache_key

    # Reservation failed: key already exists in cache (in-flight or completed)
    cached_data = cache.get(cache_key)
    if cached_data == "in-flight":
        return (
            Response(
                {"detail": "Request currently in progress."},
                status=status.HTTP_409_CONFLICT,
            ),
            cache_key,
        )

    if isinstance(cached_data, dict) and "data" in cached_data and "status" in cached_data:
        return Response(cached_data["data"], status=cached_data["status"]), cache_key

    # In case cached_data expired right between cache.add and cache.get:
    if cache.add(cache_key, "in-flight", timeout=ttl):
        return None, cache_key

    return (
        Response(
            {"detail": "Request currently in progress."},
            status=status.HTTP_409_CONFLICT,
        ),
        cache_key,
    )


def store_idempotency(cache_key, response, ttl=300):
    """Store successful 2xx response in cache for idempotency key, or release reservation on failure."""
    if not cache_key:
        return
    if response and 200 <= response.status_code < 300:
        cache.set(
            cache_key,
            {"data": response.data, "status": response.status_code},
            timeout=ttl,
        )
    else:
        # If the request resulted in an error or was aborted, release the reservation
        if cache.get(cache_key) == "in-flight":
            cache.delete(cache_key)


def clear_idempotency(cache_key):
    """Explicitly release idempotency reservation or entry from cache."""
    if cache_key:
        cache.delete(cache_key)
