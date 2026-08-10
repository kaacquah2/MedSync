# ADR-002: Session and Token Strategy

**Date:** 2026-06-26
**Status:** Accepted

## Context

The system must authenticate users and maintain session state. Options considered:
1. **Django server-side sessions** (default; session key in cookie, state in DB).
2. **JWT access + refresh tokens** (djangorestframework-simplejwt with rotation + blacklist).
3. **Opaque API tokens** (Django REST Framework's `TokenAuthentication`).

The checklist notes that token strategy must support **instant revocation** for terminated or compromised accounts.

## Decision

Use **Django's built-in server-side sessions** stored in the PostgreSQL database.

- Session key stored in a `Secure; HttpOnly; SameSite=Lax` cookie.
- Session data lives in `django_session` table; deleting a row immediately invalidates the session.
- `SESSION_COOKIE_AGE = 3600` (1 hour idle timeout); `SESSION_SAVE_EVERY_REQUEST = True` resets the timer on activity.
- CSRF protection applies to all state-changing requests (Django default).

## Rationale

- **Instant revocation**: deleting a session row (or calling `user.session_set.all().delete()`) terminates all of that user's sessions immediately. JWTs require a blacklist; short-lived JWTs add operational complexity with no benefit for a server-rendered app.
- **No XSS token theft risk**: tokens never touch JavaScript (no `localStorage`). The HttpOnly cookie is inaccessible to scripts.
- **Simplest implementation**: no DRF/React needed; aligns with the server-rendered architecture decision.
- **MFA integration**: `session['otp_verified']` and the trusted-device signed cookie layer cleanly on top.

## Consequences

- Horizontal scaling requires a shared session store (Redis or PostgreSQL with PgBouncer). Documented in the scalability note; acceptable for the single-instance prototype.
- If a DRF API layer is added in the future, session authentication is compatible (`SessionAuthentication` in DRF) or JWT can be layered on top.

## What a real production deployment would add

- Move sessions to **Redis** (faster, TTL-native, horizontally shared across app nodes).
- Consider short-lived JWTs for any future mobile client where cookie handling is constrained.
- Badge-tap SSO (Imprivata/SAML) for clinical workstations — TOTP becomes the remote/admin channel only.
