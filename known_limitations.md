# Known Security & Performance Limitations

This document lists the architectural trade-offs, scalability limits, and design choices in the current prototype iteration of **mEd**.

---

## 1. Encrypted Search: Trigram Tokens & Name Encryption Trade-offs

### Mechanism
To support partial/substring lookups without performing $O(N)$ sequential memory decryption across the entire patient registry, mEd uses a two-tier indexing architecture:
* **Exact match search**: Evaluates `name_hash` and `national_id_hash` via deterministic `HMAC-SHA256(BLIND_INDEX_KEY, normalised_plaintext)`.
* **Partial / substring search**: In `Patient.save()`, `generate_name_trigrams()` computes 3-character substrings across first and last names. These are saved into `PatientSearchToken` as `HMAC-SHA256(BLIND_INDEX_KEY, trigram)`. Query terms are similarly tokenized and resolved using indexed SQL set intersections.

### Limitation & Security Trade-offs
* **Low-Entropy Keyspace Leakage**: The total keyspace for lowercase Latin 3-character tokens is only $26^3 \approx 17,576$.
* **Precomputed Dictionary / Rainbow Table Attack**: An adversary holding a database backup and `BLIND_INDEX_KEY` can precompute HMAC hashes for the entire trigram universe in milliseconds. By matching hashes in `PatientSearchToken`, an attacker can reconstruct patient names directly from the token rows without ever decrypting the primary Fernet ciphertext columns (`first_name`, `last_name`).
* **Frequency Analysis without the Key**: Even if `BLIND_INDEX_KEY` remains secure, trigram co-occurrence patterns across patient rows can be matched against public census or demographic name distributions to de-anonymize names via statistical frequency analysis.
* **Net Effect**: Primary demographics are encrypted with Fernet AES-128-CBC at rest, but the partial search index inherently trades cryptographic confidentiality for indexable search performance.

### Mitigations & Production Controls
1. **Strict Key Separation**: `BLIND_INDEX_KEY` must be generated independently from `SECRET_KEY` and `FIELD_ENCRYPTION_KEY`. `core.blind_index._get_key()` actively blocks startup in production (`DEBUG=False`) if `BLIND_INDEX_KEY` is missing or duplicates `SECRET_KEY`.
2. **Key Rotation**: If `BLIND_INDEX_KEY` is compromised or rotated, administrators run `python manage.py reindex_blind` to re-hash all `PatientSearchToken` rows and blind index columns.
3. **RBAC & Search Scoping**: Non-administrative users are strictly restricted to searching patients registered at their own hospital. Every search query generates a tamper-evident audit record (`SEARCH_PATIENT`) containing a query hash and result count.
4. **Future Architectural Roadmap**:
   * **Higher Token Granularity**: Migrating to 4-grams ($26^4 = 456,976$) or 5-grams ($26^5 \approx 11.88\text{M}$) exponentially enlarges the keyspace against offline attacks, at the expense of requiring longer search queries.
   * **Strict Exact-Match Policy**: Enforcing search by exact identifier (NHID or National ID) for routine lookups, disabling fuzzy substring matching entirely for non-privileged users.
   * **Searchable Symmetric Encryption (SSE)**: Integrating cryptographically formal searchable encryption schemes with bounded leakage profiles.


---

## 2. Audit Log Concurrency & Advisory Locks

### Mechanism
To guarantee the chronological order and cryptographic sequence of the audit log chain, the system executes audit writes synchronously within the request transaction under serialization guards:
* On PostgreSQL, it obtains a session-level transactional advisory lock (`pg_advisory_xact_lock` using fixed ID `0x6D456400`) before querying the preceding entry's hash, computing `row_hash = sha256(prev_hash + canonical_fields)`, and inserting into `audit_auditlog`.
* On SQLite (used in development/test), table-level locking provides serialization.

### Limitation & Trade-Offs
* **Serialization bottleneck**: Because only one transaction across all Gunicorn workers can hold the advisory lock at a time, audit log writes are strictly serialized. In high-concurrency deployments with multiple application workers or container replicas, this lock introduces transaction wait latency and request queuing.
* **Why naive in-memory async queues fail (HIPAA non-compliance)**: Mitigating this latency by shunting audit entries into an in-process memory queue (e.g., Python `queue.Queue` with a background daemon thread) is fundamentally flawed:
  * **Silent loss on shutdown, crash, or deploy**: In-flight audit events are silently dropped on worker recycling, OOM kills, rolling deploys, or ungraceful terminations (`SIGKILL`). Critical compliance events—such as `BREAK_GLASS`, `ACCESS_DENIED`, and `DOWNLOAD_DOCUMENT`—are permanently lost. HIPAA §164.312(b) mandates an audit trail that records and examines activity in systems that contain or use EPHI; "best-effort" in-memory logging does not meet this durability requirement.
  * **Unbounded memory**: Unbounded in-memory queues risk process OOM crashes during sudden request spikes.
  * **Log-before-commit & transaction decoupling**: An in-memory queue writes entries independently of whether the outer request transaction committed or rolled back.
  * **Unsaved instance trap**: Asynchronous queuing causes `log_action()` to return an unsaved model instance (`entry.pk is None`), breaking callers that rely on the persisted audit entry identifier.

### Production Mitigations
For systems requiring throughput beyond what synchronous PostgreSQL advisory locks support:
1. **Durable message broker**: Push audit events synchronously to a dedicated, persistent append-only broker (e.g., Apache Kafka, AWS SQS FIFO, or Google Cloud Pub/Sub with persistent storage). Requests wait only for broker disk acknowledgment, and an isolated, single-threaded consumer appends entries sequentially to the cryptographic ledger.
2. **Two-phase asynchronous sealing**: Insert audit records synchronously inside the request transaction with empty hash fields, then run an asynchronous sealing daemon that walks unsealed rows in primary-key order to populate `prev_hash` and `row_hash`. (Note: This requires relaxing the database `BEFORE UPDATE` trigger on hash columns specifically for the sealing role).
3. **Database partitioning**: Partition `audit_auditlog` by date or tenant and checkpoint cryptographic anchor receipts per partition.

---

## 3. Audit Log Retention & Hash-Chain Integrity

### Mechanism
The `prune_audit_logs` management command prunes records older than a configured age (e.g., 30 days) to prevent unbounded storage growth.

### Limitation & Trade-Offs
* **Chain breaks**: Because each audit row is cryptographically linked to the previous row (`row_hash = sha256(prev_hash + content)`), deleting older entries naturally breaks the integrity chain. The validation tool can only verify the chain starting from the first remaining row's primary key, and the overall historical continuity is lost.
* **Production mitigation**: Instead of deleting rows from the active database table, utilize **database partitioning** (e.g., monthly partitions). When a partition becomes cold:
  1. Calculate and sign a cryptographic receipt of the final state of the partition.
  2. Archive the raw partition to read-only, write-once-read-many (WORM) cloud storage (e.g. Amazon S3 Object Lock, Google Cloud Storage Bucket Lock).
  3. Drop the partition from the transactional database.

---

## 4. Staff PII Plaintext Storage

### Mechanism
Clinical fields (encounters, diagnoses, prescriptions, lab results, referrals) and patient demographics are encrypted using Fernet at rest. However, staff profiles (User table containing first name, last name, email) are stored in plaintext.

### Limitation & Trade-Offs
* **PII exposure**: If the database is compromised, staff member identities and email addresses are visible in plaintext. This is a design choice in this prototype to facilitate authentication backend matching, Django admin views, and direct staff listing/search.
* **Production mitigation**: Apply the same field-level encryption helper (`EncryptedCharField`) to staff demographic columns, and query them via deterministic blind index hashing for exact matching (e.g. email lookup during login).

---

## 5. Clinical Document Hard Deletion & Retention Compliance

### Mechanism
When a document attached to a patient (`PatientDocument`) is deleted via `DELETE /api/patients/<nhid>/documents/<pk>/`, the endpoint enforces role authentication (`IsAdminOrClinical`) alongside patient hospital access permissions (`can_access_patient`). Upon authorization, the view deletes the physical file from the storage backend (`doc.file.delete(save=False)`) and permanently deletes the database record in an atomic transaction, recording a `DELETE_DOCUMENT` audit event in the audit log.

### Limitation & Trade-Offs
* **Irreversible Destruction vs. Statutory Retention**: Under healthcare regulatory standards (such as HIPAA §164.316 or national clinical record retention regulations requiring medical records to be maintained for statutory periods, often 5–10+ years), physical and metadata destruction of clinical attachments (e.g. diagnostic imaging, discharge summaries, consent forms) directly by clinical users poses compliance and clinical continuity risks. Although the action is permanently audited in the cryptographic ledger, the underlying document payload and record are unrecoverable.
* **Absence of Soft-Delete / Tombstoning**: The prototype does not maintain a soft-delete lifecycle (e.g., `is_deleted`, `deleted_at`, `deleted_by`) or an archival / quarantine state.

### Production Mitigations
1. **Administrative Privilege Gating**: Restrict document deletion strictly to administrative roles (`IsHospitalAdmin` / `IsSystemAdmin`) or implement a dual-custody approval flow.
2. **Soft Deletion & Tombstoning**: Transition `PatientDocument` to a soft-delete model where deleted records are hidden from routine clinical queries but preserved in storage until legal retention windows elapse.
3. **WORM / Versioned Storage**: Back `patient_documents/` with Object Lock (WORM) or version-enabled cloud object storage (e.g., AWS S3 Object Lock, GCP Cloud Storage retention policies) to prevent permanent destruction of underlying binaries.

---

## 6. Global Session Invalidation & Unindexed Session Scans

### Mechanism
The `SignoutAllView` (`POST /api/security/signout-all/`) allows a user to terminate all other active web sessions across all devices (for instance, following a password change or suspected account compromise). The endpoint queries all unexpired sessions in the database (`django.contrib.sessions.models.Session`), iterates through them using a cursor, decodes each session payload (`session.get_decoded()`), checks if `_auth_user_id` matches the calling user's primary key, and deletes matching sessions.

### Limitation & Trade-Offs
* **$O(\text{all unexpired sessions})$ Full-Table Scan**: Django's standard session engine stores session payloads as serialized, base64-encoded blobs in a single table without an indexed foreign key to `User`. Finding a specific user's sessions therefore requires decrypting/decoding every unexpired session row in the entire database.
* **Scalability Bottleneck**: In a large-scale deployment with tens of thousands of active concurrent sessions, calling `signout-all` can cause significant database and CPU overhead due to sequential row decoding.

### Production Mitigations
1. **Custom Session Model with Indexed `user_id`**: Inherit from `AbstractBaseSession` and add a foreign key / indexed `user_id` column that is automatically populated when sessions are saved. This reduces lookups to an indexed $O(1)$ query (`UserSession.objects.filter(user=user).delete()`).
2. **Redis-Backed Session Management**: In high-throughput deployments, use a Redis session backend (or Django-Redis) with a secondary index mapping `user_id -> set(session_keys)` for instantaneous $O(1)$ multi-device revocation.
3. **MFA Trust Invalidation**: `SignoutAllView` already increments `user.mfa_trust_version`, which immediately invalidates all active trusted-device cookies for that user, ensuring that even if session cleanup were delayed, elevated device trust is severed immediately.

