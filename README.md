# MyPIMA FastAPI Backend

A FastAPI backend for the MyPIMA frontend. This service is **not** the ETL service.  
It is a **CRUD API** over the existing Postgres database, with:

- Domain-driven structure (one domain per DB table)
- JWT authentication
- Role + project scoping using `users.user_role` and `project_staff_roles`
- Server-side pagination (`page`, `page_size`, default 10) matching the frontend
- CommCare re-sync flags behavior required by MyPIMA

---

## 1) Tech Stack

- FastAPI
- SQLAlchemy 2.0 (async) + asyncpg
- Postgres (existing schema)
- passlib bcrypt
- python-jose (JWT)

---

## 2) Project Structure (DDD per entity)

Each database table is treated as its own domain:

```
app/
  main.py
  api/router.py
  auth/
    router.py
    deps.py
    rbac.py
    security.py
  core/
    config.py
    logging.py
    pagination.py
  db/
    session.py
    reflection.py
  shared/
    crud.py
    domain_factory.py
    scoping.py
    project_resolution.py
    exceptions.py
    responses.py
  domains/
    farmers/
      models.py
      schemas.py
      repository.py
      service.py
      router.py
    ...
```

### Reflection-based models
This backend reflects your live DB schema at startup (`MetaData.reflect`).  
That means it works cleanly against the real database without hardcoding 200+ columns in code.

---

## 3) Configuration

Copy `.env.example` to `.env` and update values.

### Required env vars

- `DATABASE_URL`
- `JWT_SECRET`
- `DB_SCHEMA` (defaults to `pima`)
- `CORS_ORIGINS`
- `COMMCARE_BASE_URL` (optional; recommended for image proxy host validation)
- `COMMCARE_USERNAME` / `COMMCARE_PASSWORD` (required for CommCare image proxy)

Example:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/pima
DB_SCHEMA=pima
JWT_SECRET=change-me
CORS_ORIGINS=*
```

---

## 4) Running locally

### Option A: local python
```bash
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Option B: Docker
```bash
cp .env.example .env
docker compose up --build
```

Health:
- `GET /health`

OpenAPI:
- `GET /docs`

---

## 5) Authentication

### Login (JWT)
`POST /api/v1/auth/login`

Body:
```json
{ "email": "user@example.com", "password": "..." }
```

Response:
```json
{ "access_token": "...", "token_type": "bearer" }
```

Use `Authorization: Bearer <token>` for all other endpoints.

### Current user
`GET /api/v1/auth/me`

---

## 6) RBAC + Project Scoping

### Roles (exact values)
These are the supported roles (same list for `users.user_role` and `project_staff_roles.role`):

- CI Leadership
- Project Manager
- Senior MEL Specialist
- MEL Specialist
- Business Advisor
- Agronomy Advisor
- Senior Agronomy Advisor
- Senior Business Advisor
- Farmer Trainer
- Super Admin

### Access rules

- **Super Admin**: unrestricted access.
- All other roles:
  - can only see records linked to projects where they have an **Active** `project_staff_roles` row.
  - project scoping is applied automatically using join paths (farmer_group → project, training_session → farmer_group → project, etc.)

### Delete rules
Only these roles can delete:
- Super Admin
- CI Leadership
- Project Manager

---

## 7) Pagination (matches frontend)

All list endpoints support:

- `page` (default 1)
- `page_size` (default 10, max 100)
- `search` (best-effort on common fields)
- `sort`
- `order=asc|desc`

Response:
```json
{
  "items": [...],
  "page": 1,
  "page_size": 10,
  "total": 123,
  "pages": 13
}
```

---

## 8) CRUD Endpoints (per entity)

Each domain exposes:

- `GET    /api/v1/<entity>?page=1&page_size=10`
- `GET    /api/v1/<entity>/{id}`
- `POST   /api/v1/<entity>`
- `PATCH  /api/v1/<entity>/{id}`
- `DELETE /api/v1/<entity>/{id}`

Examples:
- `/api/v1/projects`
- `/api/v1/farmer_groups`
- `/api/v1/training_sessions`
- `/api/v1/wetmills`

---

## 9) CommCare re-sync flags behavior (your requirement)

### A) On update (PATCH), force `send_to_commcare = true`
For these entities:

- `project_staff_roles` (project_roles)
- `farmer_groups`
- `farmers`
- `training_sessions`

Any PATCH call will automatically set:
- `send_to_commcare = true` (if column exists)
- `send_to_commcare_status = "Pending"` (if column exists)

### B) On training_modules update, cascade flags
When `training_modules` is updated:
- set **all** `project_staff_roles` for the same project to `send_to_commcare = true`
- set **all** `training_sessions` for the same project to `send_to_commcare = true` (via farmer_groups)

This logic lives in:
- `app/domains/training_modules/service.py`

---

## 10) Notes / Limitations

- Because the API uses reflection, the request/response payloads are generic JSON dictionaries.
- If you want strict typed schemas per entity (Pydantic models with every column), we can generate them from your DB schema dump, but it creates a lot of code and is harder to maintain.

---

## 11) Next recommended improvements (optional)

- Alembic migrations scaffold (if you want the API to manage schema changes)
- structured JSON logging for GCP
- request tracing / correlation IDs
- finer-grained permissions per route (beyond delete restriction)


### Data verification image proxy

For sampled training sessions, image URLs can be returned as backend proxy URLs:

- `GET /api/v1/data-verification/training-sessions/image/{commcare_image_id}.jpg`

The backend resolves the stored CommCare attachment URL and fetches the image using `COMMCARE_USERNAME` and `COMMCARE_PASSWORD`.
