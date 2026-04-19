# Database Setup — Furniture Store Backend

## Prerequisites

- PostgreSQL 14+ installed and running
- Python 3.11+ with a virtual environment activated
- `psql` CLI available in PATH

---

## 1. Create the PostgreSQL Database

```bash
psql -U postgres
```

Inside the psql prompt:

```sql
CREATE DATABASE furniture_store;
\q
```

---

## 2. Configure the `.env` File

Create `E-Commerce-Backend/.env` with the following contents:

```env
# Database
DATABASE_URL=postgresql://postgres:<your_password>@localhost:5432/furniture_store

# JWT
SECRET_KEY=f1e4ec2f55bfbb2998d97b5bd4e4251605d890540ff8eb5990b61696fc8192a7
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Stripe (replace with real keys for production)
STRIPE_SECRET_KEY=sk_test_your_stripe_key_here
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret_here

# File Upload
UPLOAD_DIR=uploads
MAX_FILE_SIZE=5242880

# CORS
ALLOWED_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

Replace `<your_password>` with your PostgreSQL password (the project uses `root`).

---

## 3. Install Python Dependencies

```bash
cd E-Commerce-Backend
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

pip install fastapi uvicorn sqlalchemy psycopg2-binary pydantic pydantic-settings \
    pydantic[email] python-jose[cryptography] passlib python-slugify \
    python-multipart httpx stripe "bcrypt==4.0.1"
```

> **Important:** Pin `bcrypt` to `4.0.1`. bcrypt 5.x is incompatible with passlib
> and causes a "no bcrypt backend" error at runtime.

---

## 4. Run the Server

SQLAlchemy creates all 17 tables automatically on first startup via
`Base.metadata.create_all(bind=engine)`.

```bash
# From inside E-Commerce-Backend/ with venv active
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

> **Windows note:** Do NOT use `--reload` on Windows. The reload subprocess uses
> the system Python (not the venv), which causes a "no bcrypt backend" error.
> Restart manually after code changes instead.

If port 8000 is occupied (even by a killed process, due to Windows stale
`netstat` entries), switch ports:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8002
```

API is available at `http://localhost:8000` (or whichever port you chose).
Swagger UI: `http://localhost:8000/docs`

---

## 5. Bootstrap the First Admin User

There is no seeded admin on a fresh database. Register a user via the API, then
promote it directly in psql:

```bash
psql -U postgres -d furniture_store
```

```sql
-- Replace the email with the one you registered
UPDATE users SET role = 'admin' WHERE email = 'admin@elamshelf.com';
\q
```

That user can now log in and use all `/api/v1/admin/*` endpoints.

---

## 6. (Optional) Set a Manager Password via SQL

If you created a manager via the API and need to set a known password, generate
a bcrypt hash using the running app first:

```python
# Quick one-liner using the app's security module
from app.core.security import hash_password
print(hash_password("manager123"))
```

Then apply the hash in psql:

```sql
UPDATE users
SET hashed_password = '<paste_hash_here>'
WHERE email = 'manager@elamshelf.com';
```

---

## Database Tables (17 total)

| Table | Description |
|---|---|
| `users` | Customers, managers, and admins |
| `categories` | Product categories (tree structure) |
| `products` | Product catalogue |
| `product_categories` | Many-to-many: products ↔ categories |
| `product_images` | Product image gallery |
| `product_videos` | Product video gallery |
| `product_variant_groups` | Variant attribute groups (e.g. Color) |
| `product_variants` | Individual variant options (e.g. Red, Blue) |
| `inventory` | Per-product stock record |
| `stock_movements` | Audit log of every stock change |
| `carts` | Active shopping carts |
| `cart_items` | Line items in a cart |
| `orders` | Customer orders |
| `order_items` | Line items in an order |
| `reviews` | Product reviews |
| `tasks` | Internal task management |
| `addresses` | Saved customer addresses |

---

## API Endpoint Summary (50 endpoints)

| Prefix | Router | Auth |
|---|---|---|
| `/api/v1/auth` | Authentication (login, register, refresh) | Public |
| `/api/v1/users` | User profile management | User+ |
| `/api/v1/categories` | Category CRUD | Public (read) / Admin (write) |
| `/api/v1/products` | Product catalogue | Public (read) / Admin (write) |
| `/api/v1/cart` | Shopping cart | User+ |
| `/api/v1/orders` | Order placement & history | User+ |
| `/api/v1/reviews` | Product reviews | User+ |
| `/api/v1/payments` | Stripe payment & webhooks | User+ |
| `/api/v1/admin` | Admin dashboard, managers, reports | Admin only |
| `/api/v1/inventory` | Stock management | Admin / Manager |
| `/api/v1/tasks` | Task CRUD | Admin / Manager |
| `/api/v1/manager` | Manager dashboard | Admin / Manager |

---

## Test Credentials (development only)

| Role | Email | Password |
|---|---|---|
| Admin | admin@elamshelf.com | admin123 |
| Manager | manager@elamshelf.com | manager123 |
