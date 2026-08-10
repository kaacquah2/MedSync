# Contributing to mEd

## Prerequisites

- Python 3.12+
- Node.js 20+
- Docker Desktop (optional — needed for `docker compose up`)

## Local setup

```bash
# Python
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy env template and fill in values (see README for key-generation commands)
cp .env.example .env

# Apply DB migrations and load demo data
python manage.py migrate
python -X utf8 manage.py seed_demo

# Frontend
cd frontend
npm ci
npm run build      # one-time build so Django can serve the SPA at /spa/
cd ..

# Start backend
python manage.py runserver
# In a separate terminal — hot-reload dev server (optional, proxies /api/* to :8000)
cd frontend && npm run dev
```

## Running tests

```bash
# Python tests (101 tests, in-memory SQLite)
pytest tests/ --tb=short -q

# Frontend tests
cd frontend && npm run test:run

# Coverage
pytest tests/ --cov=. --cov-report=html
cd frontend && npm run coverage
```

## Code style

```bash
# Python — ruff lint + format check
ruff check .
ruff format --check .

# Frontend — ESLint + TypeScript
cd frontend
npm run lint
npm run typecheck
```

CI enforces all of the above on every push. The pipeline must be green before merging.

## Adding a Django app

1. Create the app with `python manage.py startapp <name>`.
2. Add `"<name>.apps.<Name>Config"` to **both** `emr/settings.py` **and** `emr/settings_test.py`.
3. Wire API endpoints in `api/urls.py`.
4. Register audit actions in `audit/constants.py`.
5. Run `python manage.py makemigrations <name>`.

## Security invariants (do not break)

- All patient data must pass through `can_access_patient()` in `access/permissions.py`.
- All mutations must call `log_action()` in `audit/utils.py`.
- PHI fields must use `EncryptedCharField` / `EncryptedTextField` from `core/fields.py`.
- Role values are always **lowercase snake_case** — never add uppercase role constants.
- `frontend/src/constants/roles.ts` is the single source of truth for role metadata.

## Pull request checklist

- [ ] `pytest tests/ -q` passes (or new tests added for new behaviour)
- [ ] `ruff check .` clean
- [ ] `npm run typecheck && npm run lint` clean in `frontend/`
- [ ] `python manage.py makemigrations --check --dry-run` exits 0 (no missing migrations)
- [ ] New Django apps added to `settings_test.py` as well as `settings.py`
- [ ] Sensitive data (`SECRET_KEY`, `FIELD_ENCRYPTION_KEY`, real patient data) not committed
