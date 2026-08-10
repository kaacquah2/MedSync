# Known Security & Performance Limitations

This document lists the architectural trade-offs, scalability limits, and design choices in the current prototype iteration of **mEd**.

---

## 1. Encrypted Search Scaling Ceiling

### Mechanism
To support secure lookup without exposing plaintext clinical identifiers in the database, mEd uses **HMAC-SHA256 blind indexing** (`name_hash` and `national_id_hash`).
* **Exact match search** is highly efficient ($O(1)$ database index lookup).
* **Fuzzy / partial search** is mathematically incompatible with deterministic blind indexes. To support user queries (e.g. typing "yaw" to find "Yaw Mensah"), the system performs a memory-capped full table scan ($O(N)$ decryption) of all records in the search scope.

### Limitation & Trade-Offs
* **Performance degradation**: Decrypting and evaluating thousands of records in memory will cause latency spikes and memory starvation at scale.
* **Production mitigation**: For larger deployments, integrate homomorphic search capabilities (e.g., cryptographically searchable indexes), prefix/trigram hashing tokenization, or restrict users strictly to exact identifier lookups (NHID / National ID).

---

## 2. Audit Log Concurrency & Advisory Locks

### Mechanism
To guarantee the chronological order and cryptographic sequence of the audit log chain, the system serializes write operations to the `audit_auditlog` table.
* On PostgreSQL, it obtains a session-level transactional advisory lock (`pg_advisory_xact_lock` using a fixed ID `0x6D456400`) before inserting rows.

### Limitation & Trade-Offs
* **Serialization bottleneck**: Since only one transaction can hold the advisory lock at a time, audit log writes are serialized. In a highly concurrent system with multiple Gunicorn workers, Celery tasks, or multiple application containers, this lock will bottleneck throughput and cause request queuing.
* **Production mitigation**: Move audit log writing to an asynchronous write-ahead log pipeline (e.g., streaming audit events to Kafka, Pub/Sub, or Kinesis), where a single dedicated worker thread appends logs to the chain sequentially, or utilize distributed ledger systems.

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
