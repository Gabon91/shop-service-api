-- Initial migration for a new Supabase project (PostgreSQL 13+).
-- Run once as postgres in the SQL Editor. Any failure rolls back all changes.
begin;

create table public.products (
    id uuid primary key default gen_random_uuid(),
    name text not null check (length(btrim(name)) > 0),
    description text,
    price double precision not null check (price >= 0 and price < 'Infinity'::double precision),
    stock integer not null default 0 check (stock >= 0),
    image_url text
);

create table public.customers (
    id uuid primary key default gen_random_uuid(),
    name text not null check (length(btrim(name)) > 0),
    email text not null unique check (length(btrim(email)) > 0),
    phone text,
    created_at timestamptz not null default now()
);

create table public.orders (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid not null references public.customers (id) on delete restrict,
    total_amount double precision not null
        check (total_amount >= 0 and total_amount < 'Infinity'::double precision),
    status text not null default 'Pending'
        check (status in ('Pending', 'Completed', 'Cancelled')),
    created_at timestamptz not null default now()
);

create index idx_orders_customer_id on public.orders (customer_id);
create index idx_orders_created_at on public.orders (created_at desc);

create table public.order_items (
    id uuid primary key default gen_random_uuid(),
    order_id uuid not null references public.orders (id) on delete cascade,
    product_id uuid not null references public.products (id) on delete restrict,
    quantity integer not null check (quantity > 0),
    price double precision not null check (price >= 0 and price < 'Infinity'::double precision)
);

create index idx_order_items_order_id on public.order_items (order_id);
create index idx_order_items_product_id on public.order_items (product_id);

comment on column public.products.price is
    'FLOAT-compatible catalog price. Floating-point storage follows the assignment contract.';
comment on column public.order_items.price is
    'Unit price captured at checkout, not the line total or the current catalog price.';
comment on column public.orders.total_amount is
    'Sum of quantity * unit price for order items; maintained by the order creation service.';

-- Only the trusted FastAPI backend may access these tables through Supabase.
-- No client-facing policies: anon/authenticated roles have no direct access.
alter table public.products enable row level security;
alter table public.customers enable row level security;
alter table public.orders enable row level security;
alter table public.order_items enable row level security;

revoke all on table public.products, public.customers, public.orders, public.order_items
    from public, anon, authenticated;
grant usage on schema public to service_role;
grant select, insert, update, delete
    on table public.products, public.customers, public.orders, public.order_items
    to service_role;

commit;
