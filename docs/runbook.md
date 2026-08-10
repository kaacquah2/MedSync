# Operations Runbook — mEd EMR

> **Audience:** system administrator or DevOps engineer responsible for deploying and maintaining the mEd EMR instance.

---

## 1. Standing up the application

### Prerequisites
- Python 3.12+, Docker (optional), a Neon (serverless Postgres) or standard Postgres instance.
- `.env` file copied from `.env.example` with all required values filled in.

### Steps

```bash
# 1. Clone and enter the repo
git clone <repo> && cd mEd

# 2. Create a virtual environment and install dependencies
python -m venv .venv && source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate                             # Windows
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env — fill in SECRET_KEY, DATABASE_URL, FIELD_ENCRYPTION_KEY, BLIND_INDEX_KEY

# 4. Generate a Fernet encryption key (if you don't have one)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Paste the output into FIELD_ENCRYPTION_KEY in .env

# 5. Run database migrations
python manage.py migrate

# 6. (Optional) Seed demo data for development/demo
python manage.py seed_demo

# 7. Create a superuser (production)
python manage.py createsuperuser

# 8. Collect static files (production)
python manage.py collectstatic --noinput

# 9. Start the application
gunicorn emr.wsgi:application --bind 0.0.0.0:8000
```

### Docker

```bash
docker compose up --build
```

---

## 2. Encryption key management

### Architecture
All patient PII and PHI is encrypted at the field level using **Fernet** (AES-128-CBC + HMAC-SHA256) via `core/fields.py`. Keys are read from the environment:

| Variable | Purpose |
|---|---|
| `FIELD_ENCRYPTION_KEYS` | Comma-separated list of Fernet keys, **new key first**. Enables rotation. |
| `FIELD_ENCRYPTION_KEY`  | Legacy single-key fallback (still supported). |

Encryption uses `MultiFernet`: **the first key encrypts**; **all keys can decrypt**. This allows rotation without downtime.

### Key escrow (CRITICAL)

> **Loss of all configured keys = permanent, irrecoverable loss of all encrypted data, including backups (which are ciphertext).**

Mitigations:
1. **Store a copy of every key ever used in a hardware security module (HSM), a secrets manager (AWS Secrets Manager / GCP Secret Manager / HashiCorp Vault), or in a sealed physical envelope kept off-site.**
2. Never store the key and the ciphertext database backup in the same location.
3. After a restore drill (see §3), confirm the key is present before decryption.

### Key rotation procedure

```bash
# 1. Generate a new Fernet key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# → new_key_string

# 2. Prepend the new key to FIELD_ENCRYPTION_KEYS in .env / your secrets manager
#    (keep the old key as a fallback — do NOT remove it yet)
FIELD_ENCRYPTION_KEYS=new_key_string,old_key_string

# 3. Restart the application (it will now encrypt with the new key, decrypt with either)

# 4. Re-encrypt all existing records with the new primary key
python manage.py reencrypt_fields
# Optionally dry-run first: python manage.py reencrypt_fields --dry-run

# 5. Verify a sample of records are readable (log in, open a patient, confirm names decrypt)

# 6. Once satisfied, remove the old key
FIELD_ENCRYPTION_KEYS=new_key_string

# 7. Restart the application again

# 8. Record the rotation date and the new key reference in your key-escrow store
```

---

## 3. Backup and restore (Disaster Recovery)

### Targets (from requirements.md)
- **RTO:** < 4 hours (full service restore from backup)
- **RPO:** < 1 hour data loss

### Backup
- **Database:** Neon provides automated daily encrypted snapshots and WAL archiving. For self-hosted Postgres: configure `pg_dump` / `pg_basebackup` + WAL archiving to a separate storage bucket.
- **Encryption keys:** stored separately from the database backup (see §2 — key escrow). Backups are useless without the key.

### Restore procedure

1. **Retrieve the backup** from the storage bucket (Neon branching, or `pg_restore` for self-hosted).
2. **Retrieve the encryption key** from the escrow store (HSM, secrets manager, or sealed physical copy). Confirm the key version matches the backup date.
3. Provision a new application instance following §1.
4. Set `DATABASE_URL` to the restored database and `FIELD_ENCRYPTION_KEY(S)` to the retrieved key.
5. Run `python manage.py migrate --run-syncdb` (creates any missing tables without destroying data).
6. Smoke-test: log in, search a patient, confirm names decrypt correctly. If you see `[decryption error]`, the key is mismatched — check escrow.
7. Update DNS / load-balancer to point to the new instance.

### Restore drill cadence
A restore drill should be conducted **quarterly** by the system administrator: restore a recent backup to an isolated environment, verify data integrity, document the result and elapsed time.

---

## 4. Disabling a staff account (leaver process)

### Using the admin UI (Hospital Admin or System Admin)
1. Log in as `HOSPITAL_ADMIN` or `SYSTEM_ADMIN`.
2. Navigate to **Administration → Staff**.
3. On the departing user's row, click the **Deactivate** button (person-minus icon).
4. Confirm the prompt. The system will:
   - Set `is_active = False` on the account.
   - **Immediately purge all active sessions** for that user (they are logged out in real time, not at the next expiry).
   - Write a `STAFF_DEACTIVATED` audit log entry.
5. Verify the user's status shows **Inactive** in the staff list.
6. A deactivated account cannot log in again (Django's `ModelBackend` blocks it) but is **never deleted** — their audit trail remains intact.

### Reactivation
Click the **Activate** button on the same row to reinstate the account.

### Emergency revocation
If the UI is unavailable:
```bash
python manage.py shell -c "
from accounts.models import User
u = User.objects.get(username='departing_user')
u.is_active = False
u.save()
"
```
Then manually delete their `django_session` rows:
```sql
DELETE FROM django_session WHERE session_data LIKE '%_auth_user_id%';
-- (More precisely: decode each row to match user_id, or use the management shell.)
```

---

## 5. Verifying the audit-log hash chain

The audit log uses a SHA-256 hash chain to detect tampering. Verify it periodically:

```bash
python manage.py verify_audit_chain
```

A clean chain prints `Chain intact (N entries)`. Any broken link indicates tampering or data corruption and should be investigated immediately.

---

## 6. MFA enrollment and reset

If a clinician loses access to their authenticator app:
1. They can sign in using a **recovery code** (issued at enrolment, visible under Profile → Security → Recovery codes).
2. If all recovery codes are exhausted, a HOSPITAL_ADMIN or SYSTEM_ADMIN can delete the user's TOTP device via **Django admin → OTP TOTP → TOTP devices**, then instruct the user to re-enroll.

---

## 8. Blind-index key rotation

Patient search is powered by HMAC-SHA256 blind indexes (`name_hash`, `national_id_hash`).  Unlike Fernet, HMAC is a one-way function — you can drop the old key immediately after recomputing the indexes.

### Rotation procedure

```bash
# 1. Generate a new random key (base64-URL, 32 bytes)
python -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
# → new_blind_key

# 2. Update BLIND_INDEX_KEY in .env / your secrets manager
BLIND_INDEX_KEY=new_blind_key

# 3. Restart the application
#    New searches immediately use the new key.
#    Existing rows still hold hashes from the OLD key → search mismatches until step 4.

# 4. Recompute all blind indexes with the new key
python manage.py reindex_blind
#    Optionally dry-run first: python manage.py reindex_blind --dry-run

# 5. Verify patient search works:
#    Log in, search a patient by name and by national ID — results should appear.

# 6. The old key can be discarded immediately (no decryption step is needed).
```

**Note:** Step 4 performs `Patient.save(update_fields=["name_hash", "national_id_hash"])` for every patient row — a non-destructive operation, but avoid running during peak hours on very large datasets.

---

## 7. Known operational constraints

- **Partial-name search** performs a Python-side decrypt scan over all patients (O(n)). On a large registry this is slow. Production should replace this with a dedicated search index. The patient search endpoint is rate-limited to 30 queries/60 s per user as a mitigation.
- **FIELD_ENCRYPTION_KEYS rotation** re-encrypts every encrypted field; do not run during peak hours on a large dataset. Run with `--dry-run` first to estimate scope.
