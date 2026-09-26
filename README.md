# Shop Service API

FastAPI backend for product browsing, customer tracking, order placement, and order status updates on Supabase/PostgreSQL.

## Stage 1: Implementation

### 1) Database schema

The versioned migrations are `sql\migrations\001_initial_schema.sql` (tables,
constraints, indexes and access controls) and `sql\migrations\002_atomic_checkout.sql`
(the atomic checkout RPC). Both have already been applied to the Supabase project
configured locally; apply them in order only for **new** projects.

| Table | Columns |
| --- | --- |
| `products` | `id` UUID PK, `name` TEXT, `description` TEXT, `price` FLOAT, `stock` INTEGER, `image_url` TEXT |
| `customers` | `id` UUID PK, `name` TEXT, `email` TEXT UNIQUE, `phone` TEXT, `created_at` TIMESTAMPTZ |
| `orders` | `id` UUID PK, `customer_id` UUID FK, `total_amount` FLOAT, `status` TEXT, `created_at` TIMESTAMPTZ |
| `order_items` | `id` UUID PK, `order_id` UUID FK, `product_id` UUID FK, `quantity` INTEGER, `price` FLOAT |

All IDs default to `gen_random_uuid()` (built into PostgreSQL 13+); timestamps
default to `now()`. Only descriptions, image URLs, and phone numbers are nullable.
Prices and totals must be finite and nonnegative; stock cannot be negative and
quantities must be positive. Names and emails cannot be blank. Email uniqueness
is case-sensitive, matching PostgreSQL TEXT and the backend's `on_conflict="email"`.
Email format validation belongs to the API. Matching customers by email is
case-sensitive.

Orders default to `Pending`; allowed statuses are `Pending`, `Completed`, and
`Cancelled`. Foreign keys prevent deleting customers or products referenced by
orders. Deleting an order cascades to its items. Foreign-key and order-date
indexes support dashboard queries. The item price is a checkout-time unit-price
snapshot. PostgreSQL `double precision` implements the requested FLOAT fields;
it is approximate, so a real payment system should use NUMERIC or integer cents.
The checkout RPC calculates totals using current product prices in a transaction
and saves the unit-price snapshot with each order item. It does not decrement or
reserve stock, and status updates do not enforce transitions.

#### Apply in Supabase

1. Create a Supabase project and wait for its database to be ready.
2. Open **SQL Editor**, create a new query, and use the `postgres` role.
3. Paste the entire contents of `sql\migrations\001_initial_schema.sql`, including
   `begin` and `commit`, and click **Run**.
4. In a new query, run `sql\migrations\002_atomic_checkout.sql`.
5. Confirm the four tables appear under the `public` schema in **Table Editor**
   and the `public.create_order(text,text,text,jsonb)` function exists.
6. Run this query to inspect the columns:

```sql
select table_name, column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public'
  and table_name in ('products', 'customers', 'orders', 'order_items')
order by table_name, ordinal_position;
```

The migration runs atomically and must be applied **once to a fresh schema**.
It deliberately fails if a table already exists rather than silently accepting
a different schema. If you already ran the old draft, do not drop tables with
data or rerun this initial migration; an incremental migration is required.
After a successful application, keep this file unchanged and add numbered
migrations for future changes. On failure, the transaction rolls back; if your
SQL session remains in an aborted transaction, run `rollback;` before retrying.
Back up existing databases before applying future migrations.

#### Database access

Row Level Security is enabled on all four tables. Direct access is revoked from
`anon`, `authenticated`, and PUBLIC; only Supabase's trusted `service_role` is
granted CRUD access. Set the backend's `SUPABASE_KEY` to the project's
**service-role key**, never an anon key. Keep it exclusively in server-side
environment variables; never put it in frontend code or commit it.

The Supabase roles already exist in hosted projects. A standalone PostgreSQL
instance needs equivalent roles before this migration can run.
These database restrictions do not authenticate FastAPI callers: business
endpoints still need API authorization before exposing real customer data.

### 2) Environment variables
Set these in your local `.env` or deployment platform:

- `SUPABASE_URL`
- `SUPABASE_KEY` (server-side service-role key)
- `DATABASE_URL` (optional; direct PostgreSQL migration access only, not used by FastAPI)
- `CORS_ORIGINS` (optional; comma-separated frontend origins, defaults to localhost ports
  5173 and 3000 plus `https://shop-ui-react.vercel.app`)

Copy `.env.example` to a local `.env` and fill in `SUPABASE_URL` and
`SUPABASE_KEY`; `.env` is Git-ignored. The application reads `.env` automatically,
or supply an alternate file using `ENV_FILE`. Environment variables override
file values. Do not put the service-role key in a client or commit it.
If Render already has a `CORS_ORIGINS` variable, it overrides the defaults.
Set its value to `https://shop-ui-react.vercel.app` (without a trailing slash)
or add localhost origins separated by commas to support local UI development.
Use exact origins, not `*`; Vercel preview URLs must be added individually if needed.

### 3) Install and run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API documentation.
Without `SUPABASE_KEY`, `/whoami` and `/health` work, but database-backed
endpoints (including `/livenss`) return `503`.

### Demo catalog

After configuring `SUPABASE_URL` and the server-side `SUPABASE_KEY`, run:

```bash
python -m scripts.seed_products --dry-run
python -m scripts.seed_products
```

The script adds 24 generated, unofficial building-brick products to Supabase
without a public product-write endpoint. Their prices and stock are
deterministic demo values, not actual LEGO products or prices. `image_url`
points to openly licensed photographs hosted by Wikimedia Commons, not to
LEGO's website. Photos are illustrative: the exact part or color may differ
from the product name. The source, creator, and license link are included in
each seeded product's description; the app should display this credit with
the image. Stable UUIDs and insert-on-conflict-do-nothing mean reruns do not
duplicate products or overwrite prices or stock. On existing seed products,
the seeder replaces only its original `placehold.co` image (or a blank URL)
and original seed description; custom names, descriptions, images, prices,
stock, and unrelated products are preserved. Viewing photos requires access
to Wikimedia Commons.

| Photo source | Creator | License |
| --- | --- | --- |
| [Light Green Lego Brick](https://commons.wikimedia.org/wiki/File:Light_Green_Lego_Brick.jpg) | Stilfehler | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| [Lego Round Brick Blue](https://commons.wikimedia.org/wiki/File:Lego_Round_Brick_Blue.jpg) | Stilfehler | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/) |
| [Lego Color Bricks](https://commons.wikimedia.org/wiki/File:Lego_Color_Bricks.jpg) | Alan Chia | [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/) |
| [Pile of lego blocks](https://commons.wikimedia.org/wiki/File:Pile_of_lego_blocks.jpg) | GTurnbull925 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| [Lego bricks](https://commons.wikimedia.org/wiki/File:Lego_bricks.jpg) | Benjamin D. Esham | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |
| [250 365 - Bricks](https://commons.wikimedia.org/wiki/File:250_365_-_Bricks_(4247555680).jpg) | Kenny Louie | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) |
| [Lego Technic gears](https://commons.wikimedia.org/wiki/File:Lego_Technic_gears_red,blue,yellow_(42457828342).jpg) | Brickset | [CC BY 2.0](https://creativecommons.org/licenses/by/2.0/) |
| [Lego WeDo 2.0 Bricks](https://commons.wikimedia.org/wiki/File:Lego_WeDo_2.0_Bricks.jpg) | Klaus-Dieter Keller | [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/) |

After seeding products, create fictional dashboard data:

```bash
python -m scripts.seed_orders --dry-run
python -m scripts.seed_orders
```

This creates four `@example.com` demo customers and eight orders through the
same atomic checkout RPC as the public API. Statuses include Pending, Completed,
and Cancelled. The script matches existing demo orders by customer email and
their product/quantity lines; normal reruns skip them and do not reset any
statuses you change for testing. It can resume missing orders, but should not
be run concurrently: the schema has no order-level seed key for concurrent
idempotency. Both seed scripts run manually; neither is part of deployment or
CI/CD.

### Versioning

`setup.py` provides installable package metadata. `app\__init__.py` contains the
single `MAJOR.MINOR.PATCH` version used by package metadata, OpenAPI, and
`GET /whoami`. For a release, increment that value: MAJOR for breaking API
changes, MINOR for backward-compatible features, PATCH for fixes. Inspect it
with `python setup.py --version`; install the project with `pip install -e .`.
`pytest` remains in `requirements.txt` for development and CI, but is not an
installation dependency of the package.

## API

- `GET /whoami`: service name and version, not authenticated-user identity.
- `GET /livenss`: reads at most one product ID through Supabase to check database
  connectivity. Returns `200 {"status":"ok","database":"connected"}` on success,
  including an empty database, or `503` on missing configuration or database
  failure. Uses `SUPABASE_URL` and `SUPABASE_KEY`, not `DATABASE_URL`. The spelling
  `/livenss` is intentional. This is a database readiness check, not proof that
  every table or checkout function is available. Database requests time out
  after 15 seconds.
- `GET /health`: process-only liveness; does not contact the database.
- `GET /api/products?search=`
- `GET /api/customers`
- `GET /api/orders?customer_id=`
- `POST /api/orders`
- `PATCH /api/orders/{id}/status`

Products search is a case-insensitive, literal name substring (including
characters such as `%` and `_`). Orders include their
customer and line items; omitting `customer_id` returns all orders. The
repository pages through Supabase results rather than stopping at its default
per-query limit.

## Order payloads

```json
{
  "customer_name": "Ada Lovelace",
  "customer_email": "ada@example.com",
  "customer_phone": "+1-555-1000",
  "items": [
    { "product_id": "11111111-1111-1111-1111-111111111111", "quantity": 2 }
  ]
}
```

The product must exist in `products`. The customer is created automatically if
the email is new; otherwise their name is updated and a supplied phone replaces
their prior phone. Omit the phone or send `null` to retain an existing phone.
Order creation takes place in **one PostgreSQL transaction**: invalid products
or a failed insert leave no customer or partial order. The server determines
the price and total; client-provided prices and totals are rejected. Empty
items, duplicate product IDs, invalid email, blank name or nonpositive/noninteger
quantity return `422`. A missing product returns `404`. The quantity limit is
2,147,483,647 per line item. Product stock is informational; orders do **not**
reserve inventory or prevent overselling.

Update status using `PATCH /api/orders/{id}/status` with
`{"status":"Completed"}` (also `Pending` or `Cancelled`). A missing order returns
`404`, and a database failure returns a sanitized `503`. The API exposes no
caller authentication: protect it before exposing customer or order endpoints
to untrusted users. Supabase RLS protects direct client access but does not
authenticate requests to this server.

### Optional purchase confirmation emails

Enable 2-step verification on your Google account and create a
[Google app password](https://support.google.com/mail/answer/185833).
Set `GMAIL_ADDRESS` to that account's email and `GMAIL_APP_PASSWORD` to its
app password (without spaces) in **Render > Web Service > Environment**, then
redeploy. Remove the old `RESEND_API_KEY` and `ORDER_EMAIL_FROM` variables.
Use the same Gmail variables in your Git-ignored `.env` for local development;
never put the app password in source or frontend code. Gmail SMTP uses
`smtp.gmail.com:587` with STARTTLS and sends from the authenticated account.

After an order commits, the API sends a plain-text confirmation containing
its order ID and total before returning the response. No email is sent for a
rejected checkout. With both variables unset, emails are disabled and
purchasing works as before; setting only one prevents the app from starting.
SMTP delivery delays the checkout response and can exceed the 10-second
connection timeout. A provider
failure is logged without leaking credentials; the already-placed order still
returns successfully, but no automatic retry is attempted. Use a database
outbox and worker if guaranteed delivery is needed.

### Tests

Run `python -m pytest -q`. Unit tests use FastAPI's TestClient and a mocked
Supabase HTTP transport; no real credentials or running database are required.
The checkout transaction's SQL assertions are in
`tests\sql\test_atomic_checkout.sql`; run those only in a **disposable**
PostgreSQL database with migrations 001 and 002 applied. That script opens a
transaction, tests grants and failure rollback, then rolls back its fixtures.

## Stage 2: CICD

### GitHub Actions
The workflow in `.github/workflows/ci.yml` runs `pytest` on every push and pull request.

### Deployment

#### Render
1. In Render, select **New > Web Service**, connect GitHub and choose
   `Gabon91/shop-service-api`, branch `main`. Use the free instance if available.
   Leave **Root Directory** empty; choose the **Python** runtime. The
   `.python-version` file pins Python 3.11, matching GitHub Actions.
2. Set **Build Command** to `pip install -r requirements.txt`.
3. Set **Start Command** to `uvicorn main:app --host 0.0.0.0 --port $PORT`.
4. Under **Environment**, set `SUPABASE_URL` to your Supabase project HTTPS
   URL and `SUPABASE_KEY` to the server-side secret key (`sb_secret_...` or
   legacy service-role key). Do not add `DATABASE_URL`; the app does not use it
   and the database migrations have already been applied. Do not commit keys.
   If `CORS_ORIGINS` is set in Render, include
   `https://shop-ui-react.vercel.app` in its comma-separated value.
5. Set **Health Check Path** to `/livenss`, which checks Supabase access, and
   **Auto-Deploy** to **After CI Checks Pass**. Render will only deploy commits
   on `main` after the GitHub Actions `test` check succeeds. Its HTTP health
   checks require a successful response within five seconds; if Supabase is
   slow or unavailable, deployment can be blocked. `/health` checks the
   process only if you intentionally prefer that behavior instead.
6. Deploy. The current service base URL is
   `https://shop-service-api-7mhs.onrender.com`; open `/whoami`,
   `/livenss`, `/api/products`, and `/docs` under that URL to verify it.
   The products endpoint should list the 24 demo products seeded in Supabase.
   On a free instance the first request after inactivity can be slow.

This is dashboard-managed deployment: **do not create a separate Render
Blueprint** for the same service. The GitHub Actions workflow runs tests but
does not hold Render credentials or invoke a deploy hook. SQL migrations are
not executed automatically on app deploy; apply new migrations separately
before deploying code that depends on them.

#### Railway / Fly.io
Use the same start command and environment variables. Ensure the service listens on `0.0.0.0` and the platform-provided port.
