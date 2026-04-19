# Furniture Store — Backend API

REST API for the ElamShelf furniture e-commerce platform, built with **FastAPI**, **PostgreSQL**, and **SQLAlchemy**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI 0.111 |
| Database | PostgreSQL + SQLAlchemy 2.0 |
| Migrations | Alembic |
| Auth | JWT (python-jose + passlib/bcrypt) |
| Payments | Stripe |
| File Storage | Local filesystem (Pillow + aiofiles) |
| Validation | Pydantic v2 |

---

## Project Structure

```
E-Commerce-Backend/
├── app/
│   ├── main.py           # App entry point, middleware, router registration
│   ├── config.py         # Settings loaded from .env
│   ├── database.py       # SQLAlchemy engine & session
│   ├── core/
│   │   ├── security.py   # Password hashing, JWT creation/verification
│   │   └── dependencies.py # FastAPI dependencies (get_db, get_current_user)
│   ├── models/           # SQLAlchemy ORM models
│   ├── schemas/          # Pydantic request/response schemas
│   ├── routers/          # Route handlers (auth, users, products, …)
│   └── utils/
│       └── file_upload.py
├── requirements.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

---

## API Endpoints

All routes are prefixed with `/api/v1`.

| Router | Prefix | Description |
|---|---|---|
| Auth | `/api/v1/auth` | Register, login, token refresh |
| Users | `/api/v1/users` | User profile management |
| Categories | `/api/v1/categories` | Product categories |
| Products | `/api/v1/products` | Product CRUD, image upload |
| Cart | `/api/v1/cart` | Shopping cart |
| Orders | `/api/v1/orders` | Order placement & history |
| Reviews | `/api/v1/reviews` | Product reviews |
| Payments | `/api/v1/payments` | Stripe payment intents & webhooks |
| Admin | `/api/v1/admin` | Admin-only management routes |

Interactive docs available at **`/docs`** (Swagger UI) and **`/redoc`**.

---

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL running locally
- (Optional) Stripe account for payment features

### 1. Clone & create virtual environment

```bash
cd E-Commerce-Backend
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/furniture_store
SECRET_KEY=replace-with-a-long-random-secret-key
STRIPE_SECRET_KEY=sk_test_your_stripe_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here
```

### 4. Create the database

```bash
psql -U postgres -c "CREATE DATABASE furniture_store;"
```

### 5. Run the server

```bash
uvicorn app.main:app --reload
```

The API will be available at **http://localhost:8000**.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:password@localhost:5432/furniture_store` | PostgreSQL connection string |
| `SECRET_KEY` | *(required)* | JWT signing secret — use a long random string in production |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `STRIPE_SECRET_KEY` | *(required for payments)* | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | *(required for webhooks)* | Stripe webhook signing secret |
| `UPLOAD_DIR` | `uploads` | Directory for uploaded product images |
| `MAX_FILE_SIZE` | `5242880` | Max upload size in bytes (5 MB) |
| `ALLOWED_ORIGINS` | `["http://localhost:3000"]` | CORS allowed origins |

---

## Running with Docker

```bash
docker-compose up --build
```

This starts both the API and a PostgreSQL container.

---

## Running Tests

```bash
pytest
```

---

## Useful URLs

| URL | Description |
|---|---|
| http://localhost:8000 | API root |
| http://localhost:8000/docs | Swagger UI |
| http://localhost:8000/redoc | ReDoc |
| http://localhost:8000/health | Health check |
| http://localhost:8000/uploads/ | Served static uploads |
