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

### 1.4 Response Timing Asymmetry & Side-Channel Trade-off (H-14)
* **Observed Timing Variance**: Queries executing exact indexed lookups (e.g. `NHID-*` or deterministic blind index on Ghana Card) complete in $<5\text{ ms}$, whereas partial searches generating character trigrams and evaluating SQL token set intersections (`INTERSECT`) take $\approx 60\text{--}90\text{ ms}$.
* **Theoretical Timing Attack**: In theory, an attacker measuring microsecond response time differentials could infer whether a search string produced an exact primary index hit or invoked the trigram token fallback.
* **Architectural Rationale Against Fixed Artificial Padding**: Introducing artificial sleep or constant-time padding (e.g. forcing every search response to wait $\ge 150\text{ ms}$) was intentionally rejected. In acute trauma resuscitation and emergency triage, adding 150ms of synthetic delay to clinical identifier lookups degrades patient care.
* **Defense-in-Depth Mitigations**:
  1. **Strict Authentication & Role Gating**: The search endpoint is closed to the public; only authenticated staff may issue queries.
  2. **Institutional Tenant Scoping**: Non-admin clinicians are strictly restricted to their own hospital's patient registry, preventing cross-tenant enumeration.
  3. **Audit Ledger & Brute-Force Rate Limiting**: Every search query generates an immutable audit record (`SEARCH_PATIENT`) containing a SHA-256 hash of the query string and returned count, while `django-axes` IP throttling prevents automated timing probes.

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

## 3. Audit Log Retention & Hash-Chain Integrity (WORM Archive-then-Anchor Pattern)

### Mechanism
To prevent unbounded database table growth while preserving the mathematical continuity and tamper-evident guarantees of the cryptographic hash chain, `mEd` implements an **Archive-then-Anchor WORM (Write-Once-Read-Many) Pattern** via the `prune_audit_logs` management command:
1. **WORM Archival**: Entries older than `--days` (default: 30) are serialized in primary-key order into canonical JSON format and written to immutable disk/object storage under `media/audit_archives/`.
2. **Cryptographic Checksumming**: The system calculates the SHA-256 digest of the entire JSON archive file (`archive_file_hash`).
3. **Receipt Anchoring**: A database receipt (`AuditLogArchiveAnchor`) records the filename, SHA-256 archive checksum, and the terminal row's primary key and hash (`last_row_pk`, `last_row_hash`).
4. **Append-Only External Ledger**: The anchor metadata is synchronously appended to an out-of-band append-only ledger file (`anchor_ledger.jsonl`).
5. **Atomic Pruning with Immutability Trigger Bypass**: Only after the archive and anchors are committed are the rows deleted from `audit_auditlog` inside an atomic transaction (temporarily lifting the PostgreSQL/SQLite immutability triggers for the pruning operation).
6. **Continuous Chain Verification**: When running `verify_audit_chain`:
   - It verifies all physical WORM archive files on disk against their stored SHA-256 checksums.
   - It validates the external append-only ledger against database `AuditLogArchiveAnchor` records to detect any retroactive anchor deletion.
   - It anchors the verification of remaining active database rows directly to the preceding archive's `last_row_hash`. Mathematical continuity across pruned boundaries is therefore preserved without chain breakage.

### Limitation & Trade-Offs
* **Local Storage Dependence in Prototype**: In the current single-server prototype implementation, WORM archive JSON files and `anchor_ledger.jsonl` are stored on the local filesystem (`settings.MEDIA_ROOT/audit_archives`). A root OS attacker with local filesystem write privileges could theoretically delete or tamper with both the database and the local archive directory simultaneously if external write-once policies are not enforced at the OS/storage level.
* **Administrative Trust**: Pruning requires elevated administrative access (`manage.py prune_audit_logs`), which temporarily disables database deletion triggers during the atomic purge.

### Production Mitigations & Cloud Hardening
1. **Cloud Object Lock (WORM Storage)**: Configure the archive storage backend to export directly to cloud object storage with compliance-mode Object Lock enabled (e.g., Amazon S3 Object Lock, Google Cloud Storage Bucket Lock with retention policies). Once written, archive files cannot be modified or deleted by any identity, including cloud root credentials, until the statutory retention period expires.
2. **Immutable External Ledgering**: Push anchor events to a tamper-proof decentralized ledger, AWS CloudTrail / QLDB, or a remote append-only syslog/SIEM daemon with separate IAM credentials.
3. **Database Partitioning**: Transition `audit_auditlog` from row-level deletion to PostgreSQL native range partitioning (e.g., monthly partitions). Cold partition tables can be exported to WORM storage and detached (`ALTER TABLE ... DETACH PARTITION`) without triggering individual row-deletion queries.

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


---

## 7. Monolithic Database & Hash-Chain Advisory Lock Scalability

### Mechanism
All participating hospitals share a single monolithic PostgreSQL database instance, using Django ORM scoping and Row-Level Security (RLS) policies for multi-tenancy. Simultaneously, all audit writes nationwide acquire a single global PostgreSQL advisory lock (`_CHAIN_LOCK_ID = 0x6D456400`) to compute a single contiguous hash chain (`row_hash = sha256(prev_hash + content)`).

### Limitation & Trade-Offs
* **Blast Radius & Incident Isolation**: In a monolithic single-database architecture, a database outage, maintenance event, or point-in-time recovery at one hospital affects all hospitals nationwide.
* **National Audit Write Bottleneck**: Under heavy concurrent write traffic across multiple hospitals, all audit log writes contend for the single global advisory lock.

### Production Mitigations & Defense Framing
1. **Per-Hospital / Tenant Hash Chains**: Partition the audit ledger into per-hospital chains, acquiring advisory locks bucketed by `hospital_id` (`0x6D456400 ^ hospital_id`). This permits concurrent audit writes across different hospitals while preserving verifiable per-hospital hash chains.
2. **Cell-Based / Multi-Region Architecture**: Deploy independent database cells per regional hospital cluster with cross-region replication for emergency Break-Glass and universal patient lookup (EMPI).


---

## 8. EMPI Phonetic Matching Full-Table Decryption Scan

### Mechanism
In [`patients/empi.py`](file:///c:/Users/OSCARPACK/Downloads/mEd/patients/empi.py), the Enterprise Master Patient Index (`match_patient()`) performs patient identity deduplication to prevent duplicate medical charts across hospitals. The matching strategy employs a multi-tiered pipeline:
1. **Deterministic Match**: Querying the primary national identifier via `national_id_hash` (HMAC-SHA256 blind index).
2. **Exact Demographic Match**: Querying `name_hash` (blind index) and verifying `date_of_birth`.
3. **Probabilistic / Phonetic Fallback**: When an exact blind-index match misses, the phonetic fallback computes Soundex codes. While candidate pre-filtering uses `PatientSearchToken` (blind-indexed name trigrams), any missing tokens or broad matches fall back to querying candidate records (`Patient.objects.all()[:500]`) and sequentially evaluating them.

### Limitation & Scalability Bottleneck
* **$O(N)$ Sequential Fernet Decryption**: Because patient demographics (`first_name`, `last_name`, and `date_of_birth`) are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256), accessing these attributes during Soundex and DOB verification decrypts every candidate instance in Python application memory.
* **CPU and Memory Saturation at Scale**: While completely imperceptible and responsive on prototype-scale datasets (dozens to low hundreds of patients), in nationwide or enterprise deployments with hundreds of thousands or millions of patients, iterating over candidate records to perform sequential symmetric decryption introduces severe CPU bottlenecks, process memory bloat, and HTTP worker timeouts.
* **Worker Process Exposure**: Transporting raw encrypted records from PostgreSQL to the Django process and decrypting hundreds of patient rows per registration check expands the memory footprint of sensitive PHI inside Gunicorn workers.

### Mitigations & Production Architecture Roadmap
To achieve sub-100ms deterministic candidate retrieval at multi-million record scale without compromising field encryption at rest:

1. **Deterministic Blind-Index Blocking Filters**:
   - Rather than relying solely on raw trigrams, implement deterministic **phonetic blocking filters** at record creation time.
   - Generate phonetic codes for names using Soundex, Metaphone, or Double-Metaphone, and persist their keyed HMACs in dedicated indexed columns:
     $$\text{blocking\_hash} = \text{HMAC-SHA256}(\text{BLIND\_INDEX\_KEY}, \text{Soundex}(\text{last\_name}))$$
   - Combine with a coarse date-of-birth blocking bucket (e.g. blind-indexed birth year or `YYYY-MM` token):
     $$\text{dob\_bucket\_hash} = \text{HMAC-SHA256}(\text{BLIND\_INDEX\_KEY}, \text{birth\_year})$$
   - Database queries then apply deterministic index equality on blocking filters:
     ```python
     candidates = Patient.objects.filter(
         soundex_last_hash=make_blind_index(soundex(last_name)),
         dob_year_hash=make_blind_index(str(dob.year)),
     )
     ```
   - This narrows candidate pools from $O(N)$ whole-table scans down to an indexed $O(1)$ SQL lookup returning a small constant $k \ll N$ candidates ($k \approx 5\text{--}20$ records).

2. **Fellegi-Sunter Multi-Pass Blocking**:
   - Production EMPIs (e.g., OpenEMR, Master Person Index) execute standardized multi-pass blocking:
     - **Pass 1**: Exact Soundex(Last Name) + Birth Year.
     - **Pass 2**: Exact Soundex(First Name) + Sex + Postal/District Code.
     - **Pass 3**: Deterministic National ID / NHID.
   - Expensive probabilistic distance functions (Jaro-Winkler, Levenshtein edit distance) are executed strictly in-memory against the tiny candidate subset isolated by the blocking pass.

3. **Asynchronous Reconciliation & Dedicated Linkage Engine**:
   - Decouple deep probabilistic linkage from synchronous clinician patient registration.
   - Synchronous registration performs exact and blocked lookups for immediate candidate warnings, while a background worker (e.g., Celery or dedicated EMPI service) runs comprehensive probabilistic matching and surfaces potential duplicate chart merge requests for administrative review.

---

## 9. Digital Signatures & Non-Repudiation for Prescriptions (Act 772 §§11–14)

### Statutory Context & Regulatory Background
Under the **Electronic Transactions Act, 2008 (Act 772 §§11–14)** and the **Health Professions Regulatory Bodies Act, 2013 (Act 857)** read alongside Pharmacy Council and Medical and Dental Council (MDC) guidelines, clinical orders and pharmaceutical prescriptions require legal non-repudiation:
* **Advanced Electronic Signatures (Act 772 §§11–12)**: When a statute requires an authenticating clinician signature on an electronic record, it is legally met only if the electronic signature:
  1. Is uniquely linked to the signatory (the licensed clinician);
  2. Is capable of identifying the signatory;
  3. Was created using means under the sole control of the signatory (e.g., private cryptographic key); and
  4. Is linked to the data in such a manner that any subsequent alteration of the underlying data (drug name, dosage, frequency, route, duration) is cryptographically detectable.
* **Prescription Evidentiary Weight**: In legal proceedings or medical malpractice inquiries, an electronic prescription without cryptographic non-repudiation cannot independently prove that the attending physician authorized the exact regimen dispensed by the pharmacy.

### Mechanism & Prototype Limitations
In the current prototype implementation of mEd (`records/models.py:Prescription`):
* **Session-Tied Identity Attribution**: When a clinician creates a prescription via the API or frontend, the record captures the authenticated user via a foreign key (`created_by = request.user`) and stamps a timestamp (`created_at`).
* **Cryptographic Tamper-Evidence Gap**: The prescription row itself lacks an asymmetric digital signature (e.g., ECDSA, RSA-PSS, or Ed25519) or cryptographic HMAC sealed at the time of creation.
* **Vulnerability to Direct Database Tampering**: While patient demographics and clinical text fields are encrypted at rest with Fernet, a privileged database administrator or compromised database role could alter the ciphertext or plain attributes (e.g., dosage or drug frequency) without automatically invalidating an authenticating signature token.
* **Lack of Independent Dispensary Verification**: A dispensing pharmacist at an external facility or pharmacy node can verify that the prescription exists within the central database, but cannot verify an offline, independently portable cryptographic signature of the prescribing physician.

### Rationale for Scoping to Future Work (Not a Pre-Defense Fix)
Implementing a legally compliant, cryptographically sound Advanced Electronic Signature scheme is a major architectural subsystem rather than a tactical bug fix:
1. **Public Key Infrastructure (PKI) & CA Dependency**: Requires a formal Root Certificate Authority (CA) and Registration Authority (RA) integration, such as the National Information Technology Agency (NITA) PKI or Ghana Health Service / MDC clinician credentialing service.
2. **Key Lifecycle & Hardware Custody**: Act 772 §12 mandates that signature creation data remain under the *sole control* of the signatory. This demands either client-side WebCrypto keypair generation backed by FIDO2/WebAuthn hardware tokens, mobile PKI authentication, or secure server-side Hardware Security Modules (HSM) with PIN/biometric authorization. Implementing a naive server-side symmetric HMAC would still fail the legal requirement for sole clinician control.
3. **Revocation & Timestamping (RFC 3161)**: Requires CRL/OCSP checking and trusted third-party cryptographic timestamping to prove validity at the exact time of signing.
4. **Canonicalization & Interoperability Standards**: Demands standardized cryptographic enveloping (CMS/CAdES, JWS/JSON Web Signature, or FHIR Provenance digital signature profiles).

Attempting an ad-hoc or superficial signature implementation immediately prior to defense risks introducing severe cryptographic vulnerabilities or failing statutory tests during examination. Scoping this to the research roadmap demonstrates architectural maturity, technical rigor, and adherence to sound engineering risk management.

### Mitigations & Production Architecture Roadmap
For production healthcare deployment, the prescription signing pipeline will be implemented as follows:
1. **Clinician Keypair Provisioning & MDC Credential Binding**:
   - Each licensed practitioner generates an asymmetric keypair (ECDSA P-256 or Ed25519) during credentialing.
   - The public key is certified by the health authority's Registration Authority (RA), embedding the clinician's Medical and Dental Council (MDC) license number in the X.509 certificate subject extension.
2. **Client-Side Cryptographic Signing (WebCrypto / FIDO2)**:
   - When finalizing a prescription order, the frontend canonicalizes the prescription payload (JSON-LD or FHIR MedicationRequest canonical representation: patient NHID, prescriber MDC number, RxNorm/ATC code, dosage, duration, instructions, and UTC timestamp).
   - The clinician signs the SHA-256 digest of the payload directly on their client device using their WebAuthn/FIDO2 hardware token or secure smartcard via the browser WebCrypto API.
   - The resulting signature, signing certificate chain, and RFC 3161 cryptographic timestamp are transmitted alongside the prescription payload.
3. **Cryptographic Sealing & Immutability**:
   - The backend validates the signature against the clinician's registered public key and active license status prior to persisting the row.
   - The prescription record becomes read-only (`status = 'SIGNED'`). Any subsequent amendment creates a distinct revocation/superseding order referencing the original signature digest.
4. **Dispensary Offline Verification**:
   - Dispensing pharmacists verify the prescription signature directly against the prescriber's public certificate, guaranteeing non-repudiation and integrity even during inter-hospital network disconnections.

---

## 10. Ephemeral Container Filesystem vs. Production S3/GCS Object Storage (C-08)

### Mechanism
Clinical file attachments uploaded by clinicians (`PatientDocument` in `records/models.py`) and cryptographic audit archives (`media/audit_archives/` generated by `manage.py prune_audit_logs`) are handled via Django's `FileSystemStorage` and written to `settings.MEDIA_ROOT` (`/app/media/`).
In local Docker development (`docker-compose.yml`), this directory is backed by a persistent named Docker volume (`media_data:/app/media`), which preserves files across container restarts.

### Limitation & Data Loss Risk on PaaS Platforms
* **Stateless Ephemeral Containers**: In cloud PaaS container environments such as Render web dynos, container filesystems are entirely ephemeral. Deploying a new Git commit, scaling workers, or restarting an idling dyno creates a fresh container filesystem from the base image.
* **Catastrophic Document Destruction**: Any patient lab report PDFs, diagnostic scans, and clinical referral letters uploaded to `/app/media/patient_documents/`—as well as WORM audit archives in `/app/media/audit_archives/`—are irreversibly destroyed on container lifecycle events.
* **Compliance Violation**: In a production healthcare system, unpersisted clinical attachments violate statutory clinical document retention laws (HIPAA §164.316 and Ghana Health Service regulations requiring clinical records to be preserved for 5–10+ years).

### Rationale for Prototype Scoping
Local filesystem storage was chosen for this capstone prototype to ensure:
1. **Zero-Cost Deployment**: The prototype can run on Render's free tier and Neon serverless Postgres without incurring recurring monthly fees for dedicated cloud disks or object stores.
2. **Offline Portability & Examiner Reproducibility**: Examiners and academic evaluators can clone the repository, run `docker compose up`, or execute test suites locally without requiring paid AWS IAM credentials or Google Cloud service accounts.
3. **Metadata Durability in Neon**: Even if the binary attachment on disk is lost during a prototype reboot, all clinical chart metadata (patient NHID, uploader, timestamp, document description, MIME type, and cryptographic audit log entry `UPLOAD_DOCUMENT`) is safely persisted in the external Neon PostgreSQL database.

### Production Mitigations & Enterprise Architecture Roadmap
1. **PaaS Persistent Disk**: On Render, persistent disk storage is enabled by configuring the `disk:` block in `render.yaml`:
   ```yaml
   disk:
     name: med-media
     mountPath: /app/media
     sizeGB: 10
   ```
2. **Cloud Object Storage (`django-storages`)**: In a production enterprise deployment, clinical files must be completely decoupled from web application compute dynos:
   - Configure `django-storages` with `boto3` (`DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"`) targeting Amazon S3, Google Cloud Storage, or Cloudflare R2.
   - Enforce Server-Side Encryption (SSE-KMS / SSE-S3) for all objects at rest.
   - Enforce S3 Object Lock (WORM / Write-Once-Read-Many) in Compliance Mode with statutory retention windows to prevent deletion even by cloud root accounts.
   - Serve sensitive files via short-lived, authenticated presigned URLs (`generate_presigned_url(ExpiresIn=300)`) rather than direct public URLs, auditing every download event.

---

## 11. Machine-to-Machine (M2M) Authentication & SMART on FHIR Backend Services (H-16)

### Mechanism
The mEd FHIR R4 API (`fhir/views.py`) exposes standardized healthcare interoperability endpoints:
- `GET /fhir/metadata`: Conformance CapabilityStatement (unauthenticated per HL7 FHIR specification §3.1.0.1).
- `GET /fhir/Patient/<nhid>/`: FHIR Patient resource representation.
- `GET /fhir/Patient/<nhid>/$everything`: FHIR Bundle enclosing patient demographics, encounters, conditions, prescriptions, lab observations, and vitals.

Access to patient FHIR resources is gated by Django session authentication (`@login_required`), RBAC validation (`doctor`, `nurse`, `lab_technician`, or admin roles), and the cross-hospital decision engine (`can_access_patient()`).

### Limitation & Interoperability Boundaries
* **Session Cookie Gating**: Interactive session cookies require browser-based login and session state management.
* **Inability to Support Headless Machine-to-Machine (M2M) Integrations**: Automated external healthcare systems—such as automated hospital laboratory analyzer interfaces (LIS), National Health Insurance Authority (NHIA) claims processing engines, or regional epidemiological surveillance bots—cannot interact with session cookies, CSRF tokens, or interactive MFA prompts.
* **CapabilityStatement Security Declaration**: The FHIR CapabilityStatement currently declares `"Session-based authentication required for all resources except /metadata"`, which does not conform to the SMART on FHIR authorization profile for automated clients.

### Rationale for Scoping to Future Work (Not a Pre-Defense Fix)
Implementing production-grade machine-to-machine FHIR authentication is a substantial architectural subsystem involving independent infrastructure rather than an in-place bug fix:
1. **SMART on FHIR Backend Services Specification (RFC 7523)**: Automated system-to-system data exchange requires implementing the SMART on FHIR Backend Services Authorization profile. External systems must authenticate by signing an asymmetric JSON Web Token (JWT) assertion using a private key (RS384 or ES384) registered in a public JWKS (JSON Web Key Set), exchanging it for an ephemeral, scoped OAuth2 bearer token (`system/Patient.read`, `system/Observation.read`).
2. **Public Key Infrastructure (PKI) & Client Registration**: Demands an administrative subsystem for client onboarding, public key rotation, and health facility credential verification.
3. **Mutual TLS (mTLS)**: High-security healthcare network federations require mTLS (RFC 8705) termination at the reverse proxy or API gateway with certificate-bound access tokens.
4. **Scope Enforcement Engine**: Demands fine-grained FHIR path-level scope validation (`system/*.read` vs `patient/*.read`).

Implementing an ad-hoc or static API token header prior to defense would create serious security risks (static shared secrets, lack of client authentication, and absence of cryptographic non-repudiation). Scoping this to Phase 2 Interoperability demonstrates adherence to international interoperability standards and sound software development lifecycle planning.

### Production Mitigations & Interoperability Roadmap
1. **SMART on FHIR Backend Services Authorization**:
   - Deploy an OAuth2 authorization server (e.g. `django-oauth-toolkit` configured with asymmetric client assertions per RFC 7523).
   - Require connecting institutions to publish their JWKS endpoint.
   - Issue short-lived (5-minute) signed JWT bearer tokens scoped to specific FHIR resource types.
2. **Reverse Proxy mTLS Enforcement**:
   - Enforce client certificate validation (mTLS) at the Nginx/Traefik reverse proxy layer, matching client certificates against the health ministry's intermediate CA.
3. **CapabilityStatement Update**:
   - Update `GET /fhir/metadata` to include SMART on FHIR OAuth2 URI extensions (`authorize`, `token`, `register`) in `.rest[0].security.service`.




