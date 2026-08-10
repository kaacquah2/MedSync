"""
Idempotency and duplicate-submission protection for API endpoints.

Prevents double-click / duplicated submissions (e.g. prescription creation, lab orders)
when an `Idempotency-Key` HTTP header is supplied by caching responses for 300 seconds.
"""

from django.core.cache import cache
from rest_framework.response import Response


def get_idempotency_key(request, scope=""):
    """
    Extract idempotency cache key if `Idempotency-Key` header is present.
    Returns None if no idempotency header was provided.
    """
    key_header = request.headers.get("Idempotency-Key") or request.META.get("HTTP_IDEMPOTENCY_KEY")
    if not key_header:
        return None

    user_id = request.user.id if request.user and request.user.is_authenticated else "anon"
    return f"idempotency:key:{user_id}:{scope}:{key_header}"


def check_idempotency(request, scope=""):
    """
    Check if a request with an Idempotency-Key header is a duplicate submission.
    Returns (cached_response, cache_key).
    """
    cache_key = get_idempotency_key(request, scope=scope)
    if not cache_key:
        return None, None

    cached_data = cache.get(cache_key)
    if cached_data:
        return Response(cached_data["data"], status=cached_data["status"]), cache_key

    return None, cache_key


def store_idempotency(cache_key, response, ttl=300):
    """Store successful 2xx response in cache for idempotency key."""
    if cache_key and response and 200 <= response.status_code < 300:
        cache.set(
            cache_key,
            {"data": response.data, "status": response.status_code},
            timeout=ttl,
        )
