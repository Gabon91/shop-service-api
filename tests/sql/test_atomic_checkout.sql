-- Standalone PostgreSQL 13+ integration test, after migrations 001 and 002.
-- Run on a disposable database as the migration owner, able to SET ROLE.
-- For psql, use ON_ERROR_STOP=1. All fixtures, helpers and grants are rolled back.
begin;

create function public._test_checkout_assert(p_ok boolean, p_message text)
returns void language plpgsql set search_path = pg_catalog as $$
begin
    if p_ok is distinct from true then
        raise exception 'Atomic checkout assertion failed: %', p_message;
    end if;
end;
$$;

create function public._test_checkout_snapshot()
returns jsonb language sql set search_path = pg_catalog as $$
    select jsonb_build_object(
        'products', (select jsonb_agg(to_jsonb(p) order by p.id) from public.products as p),
        'customers', (select jsonb_agg(to_jsonb(c) order by c.id) from public.customers as c),
        'orders', (select jsonb_agg(to_jsonb(o) order by o.id) from public.orders as o),
        'items', (select jsonb_agg(to_jsonb(i) order by i.id) from public.order_items as i)
    );
$$;

create function public._test_checkout_reject(
    p_name text, p_email text, p_phone text, p_items jsonb, p_state text
)
returns void language plpgsql set search_path = pg_catalog as $$
declare
    v_before jsonb := public._test_checkout_snapshot();
    v_state text;
begin
    begin
        perform public.create_order(p_name, p_email, p_phone, p_items);
    exception when others then
        get stacked diagnostics v_state = returned_sqlstate;
    end;
    perform public._test_checkout_assert(v_state = p_state,
        format('expected SQLSTATE %s, received %s for %s', p_state, coalesce(v_state, 'success'), p_items));
    perform public._test_checkout_assert(public._test_checkout_snapshot() = v_before,
        'rejected checkout must leave every table unchanged');
end;
$$;

insert into public.products (id, name, price, stock) values
    ('00200000-0000-4000-8000-000000000001', 'Checkout decimal', 0.1, 0),
    ('00200000-0000-4000-8000-000000000002', 'Checkout second', 2.5, 7),
    ('00200000-0000-4000-8000-000000000003', 'Checkout maximum', '1.7976931348623157e308', 0),
    ('00200000-0000-4000-8000-000000000004', 'Checkout zero', 0, 0),
    ('00200000-0000-4000-8000-000000000005', 'Checkout large', '1e308', 0),
    ('00200000-0000-4000-8000-00000000000a', 'Checkout UUID alias', 1, 0);

do $$
declare
    v_oid oid := 'public.create_order(text,text,text,jsonb)'::regprocedure;
begin
    perform public._test_checkout_assert(
        (select not p.prosecdef
                and p.proconfig @> array['search_path=pg_catalog', 'extra_float_digits=3']
         from pg_catalog.pg_proc as p where p.oid = v_oid),
        'RPC must be SECURITY INVOKER with search_path=pg_catalog');
    perform public._test_checkout_assert(
        pg_catalog.has_function_privilege('service_role', v_oid, 'EXECUTE')
        and not pg_catalog.has_function_privilege('anon', v_oid, 'EXECUTE')
        and not pg_catalog.has_function_privilege('authenticated', v_oid, 'EXECUTE'),
        'only backend role may execute RPC');
    perform public._test_checkout_assert(
        not exists (
            select 1 from pg_catalog.pg_proc as p,
                lateral pg_catalog.aclexplode(coalesce(p.proacl, pg_catalog.acldefault('f', p.proowner))) as a
            where p.oid = v_oid and a.grantee = 0 and a.privilege_type = 'EXECUTE'
        ), 'PUBLIC must not have EXECUTE');
    raise notice 'PASS: RPC privileges, SECURITY INVOKER and safe search_path';
end;
$$;

set local role service_role;
-- The caller's path must not be required by the RPC.
set local search_path = pg_catalog;

do $$
declare
    v_result jsonb;
    v_reused jsonb;
    v_changed jsonb;
    v_case jsonb;
    v_expected jsonb;
    v_customer uuid;
    v_order uuid;
    v_quantity integer;
    v_bad jsonb;
    v_text text;
    v_one jsonb := '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":3}]';
begin
    v_result := public.create_order('SQL Checkout', 'atomic-checkout@example.invalid', '111', v_one);
    v_customer := (v_result ->> 'customer_id')::uuid;
    v_order := (v_result ->> 'id')::uuid;
    select to_jsonb(o) || jsonb_build_object(
        'customer', to_jsonb(c),
        'items', (select jsonb_agg(to_jsonb(i)) from public.order_items as i where i.order_id = o.id)
    ) into v_expected
    from public.orders as o join public.customers as c on c.id = o.customer_id
    where o.id = v_order;
    perform public._test_checkout_assert(v_result = v_expected, 'RPC returns the complete persisted OrderRead');
    perform public._test_checkout_assert(
        (v_result ->> 'total_amount')::numeric = 0.3
        and v_result ->> 'status' = 'Pending'
        and v_result ->> 'created_at' is not null
        and v_result #>> '{customer,name}' = 'SQL Checkout'
        and v_result #>> '{customer,email}' = 'atomic-checkout@example.invalid'
        and v_result #>> '{customer,phone}' = '111'
        and v_result #>> '{customer,created_at}' is not null
        and (v_result #>> '{items,0,price}')::numeric = 0.1
        and (v_result #>> '{items,0,quantity}')::integer = 3,
        'new customer, defaults, unit snapshot and decimal 0.1 * 3 = 0.3');
    perform public._test_checkout_assert(
        (select stock = 0 from public.products where id = '00200000-0000-4000-8000-000000000001'),
        'zero-stock product can be ordered without decrement');

    v_reused := public.create_order('Renamed Checkout', 'atomic-checkout@example.invalid', null, v_one);
    perform public._test_checkout_assert(
        (v_reused ->> 'customer_id')::uuid = v_customer
        and v_reused #>> '{customer,name}' = 'Renamed Checkout'
        and v_reused #>> '{customer,phone}' = '111'
        and v_reused #>> '{customer,created_at}' = v_result #>> '{customer,created_at}'
        and v_reused ->> 'id' <> v_result ->> 'id'
        and (select count(*) = 1 from public.customers where email = 'atomic-checkout@example.invalid'),
        'reuse customer, update name, preserve null-input phone and creation timestamp');
    v_changed := public.create_order('Updated Checkout', 'atomic-checkout@example.invalid', '222', v_one);
    perform public._test_checkout_assert(
        (v_changed ->> 'customer_id')::uuid = v_customer
        and v_changed #>> '{customer,name}' = 'Updated Checkout'
        and v_changed #>> '{customer,phone}' = '222', 'non-null phone updates existing customer');
    v_case := public.create_order('Distinct Case', 'Atomic-checkout@example.invalid', null, v_one);
    perform public._test_checkout_assert(
        (v_case ->> 'customer_id')::uuid <> v_customer
        and v_case #>> '{customer,email}' = 'Atomic-checkout@example.invalid'
        and v_case #> '{customer,phone}' = 'null'::jsonb, 'email matching is case-sensitive; new phone may be null');

    update public.products set price = 0.2 where id = '00200000-0000-4000-8000-000000000001';
    v_changed := public.create_order('Updated Checkout', 'atomic-checkout@example.invalid', null,
        '[{"product_id":"00200000-0000-4000-8000-000000000002","quantity":2,"price":-999},
          {"product_id":"00200000-0000-4000-8000-000000000001","quantity":3,"price":0}]');
    perform public._test_checkout_assert(
        (v_changed ->> 'total_amount')::numeric = 5.6
        and jsonb_array_length(v_changed -> 'items') = 2
        and v_changed #>> '{items,0,product_id}' = '00200000-0000-4000-8000-000000000002'
        and (v_changed #>> '{items,0,price}')::numeric = 2.5
        and (v_changed #>> '{items,1,price}')::numeric = 0.2
        and (select price = 0.1 from public.order_items where order_id = v_order),
        'catalog prices override payload; old unit snapshot persists; reversed input order works');
    select to_jsonb(o) || jsonb_build_object(
        'customer', to_jsonb(c),
        'items', (select jsonb_agg(to_jsonb(i) order by i.product_id desc)
                  from public.order_items as i where i.order_id = o.id)
    ) into v_expected
    from public.orders as o join public.customers as c on c.id = o.customer_id
    where o.id = (v_changed ->> 'id')::uuid;
    perform public._test_checkout_assert(v_changed = v_expected, 'multi-item response contains every persisted row field');
    perform public._test_checkout_assert(
        (select stock = 7 from public.products where id = '00200000-0000-4000-8000-000000000002'),
        'positive stock also remains unchanged');

    foreach v_quantity in array array[1, 2147483647] loop
        v_changed := public.create_order('Boundary', 'atomic-boundary@example.invalid', null,
            jsonb_build_array(jsonb_build_object('product_id', '00200000-0000-4000-8000-000000000004',
                                               'quantity', v_quantity)));
        perform public._test_checkout_assert(
            (v_changed ->> 'total_amount')::numeric = 0
            and (v_changed #>> '{items,0,quantity}')::integer = v_quantity,
            'integer quantity boundaries and free products');
    end loop;
    perform set_config('extra_float_digits', '-15', true);
    v_changed := public.create_order('Boundary', 'atomic-boundary@example.invalid', null,
        '[{"product_id":"00200000-0000-4000-8000-000000000003","quantity":1}]');
    perform public._test_checkout_assert(
        (v_changed ->> 'total_amount')::double precision = '1.7976931348623157e308'::double precision
        and current_setting('extra_float_digits') = '-15',
        'maximum finite total is accepted independently of caller float formatting, which is restored');
    perform set_config('extra_float_digits', '3', true);
    raise notice 'PASS: 8 successful checkouts; complete responses, customer reuse/case, prices, totals, stock and boundaries';

    -- Every rejection compares all four tables, including existing customer values.
    foreach v_text in array array[null::text, '', '   ', E'\t\n\r'] loop
        perform public._test_checkout_reject(v_text, 'atomic-checkout@example.invalid', 'bad', v_one, 'PT400');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad', v_one, 'PT400');
    end loop;
    foreach v_bad in array array[null::jsonb, 'null'::jsonb, '{}'::jsonb, 'true'::jsonb,
                                '1'::jsonb, '"items"'::jsonb, '[]'::jsonb] loop
        perform public._test_checkout_reject('Bad Name', 'atomic-checkout@example.invalid', 'bad', v_bad, 'PT400');
    end loop;
    for v_bad in select value from jsonb_array_elements(
        '[null,{},true,1,"item",[],{"product_id":"00200000-0000-4000-8000-000000000001"},
          {"quantity":1}]'::jsonb)
    loop
        perform public._test_checkout_reject('Bad Name', 'atomic-checkout@example.invalid', 'bad',
            jsonb_build_array(v_bad), 'PT400');
    end loop;
    for v_bad in select value from jsonb_array_elements(
        '[null,true,false,"1","",0,-1,1.0,1.5,2147483648,999999999999999999999999999999,[],{}]'::jsonb)
    loop
        perform public._test_checkout_reject('Bad Name', 'atomic-checkout@example.invalid', 'bad',
            jsonb_build_array(jsonb_build_object('product_id', '00200000-0000-4000-8000-000000000001',
                                               'quantity', v_bad)), 'PT400');
    end loop;
    for v_bad in select value from jsonb_array_elements('[null,true,1,{},[],"","not-a-uuid"]'::jsonb)
    loop
        perform public._test_checkout_reject('Bad Name', 'atomic-checkout@example.invalid', 'bad',
            jsonb_build_array(jsonb_build_object('product_id', v_bad, 'quantity', 1)), 'PT400');
    end loop;

    foreach v_text in array array['atomic-checkout@example.invalid', 'atomic-rejected-new@example.invalid'] loop
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":1},
              {"product_id":"00200000-0000-4000-8000-000000000001","quantity":2}]', 'PT409');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-00000000000a","quantity":1},
              {"product_id":"00200000-0000-4000-8000-00000000000A","quantity":2}]', 'PT409');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":1},
              {"product_id":"00200000-0000-4000-8000-000000000001","quantity":"2"}]', 'PT400');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-000000000099","quantity":1}]', 'PT404');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":1},
              {"product_id":"00200000-0000-4000-8000-000000000099","quantity":1}]', 'PT404');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-000000000003","quantity":2}]', 'PT400');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-000000000003","quantity":1},
              {"product_id":"00200000-0000-4000-8000-000000000005","quantity":1}]', 'PT400');
        perform public._test_checkout_reject('Bad Name', v_text, 'bad',
            '[{"product_id":"00200000-0000-4000-8000-000000000003","quantity":1},
              {"product_id":"00200000-0000-4000-8000-000000000002","quantity":2147483647},
              {"product_id":"00200000-0000-4000-8000-000000000001","quantity":null}]', 'PT400');
    end loop;
    raise notice 'PASS: 59 input/domain rejections; PT400/PT404/PT409 and full-table rollback checks';
end;
$$;

reset role;

-- An AFTER STATEMENT trigger proves that customer, order AND item writes happened
-- before throwing. Its exception must unwind the entire RPC, not just item writes.
create function public._test_checkout_injected_failure()
returns trigger language plpgsql set search_path = pg_catalog as $$
begin
    if not exists (
        select 1 from public.order_items as i
        join public.orders as o on o.id = i.order_id
        join public.customers as c on c.id = o.customer_id
        where c.name = 'Injected Failure' and c.phone = 'injected'
    ) then
        raise exception 'Failure injection did not observe all checkout writes';
    end if;
    raise exception using errcode = 'PT499', message = 'Injected failure after all checkout writes';
end;
$$;
create trigger test_checkout_injected_failure
after insert on public.order_items
for each statement execute function public._test_checkout_injected_failure();

set local role service_role;
do $$
declare
    v_email text;
begin
    foreach v_email in array array['atomic-checkout@example.invalid', 'atomic-injected-new@example.invalid'] loop
        perform public._test_checkout_reject('Injected Failure', v_email, 'injected',
            '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":2},
              {"product_id":"00200000-0000-4000-8000-000000000002","quantity":1}]', 'PT499');
    end loop;
    raise notice 'PASS: 2 injected post-write failures roll back new/reused customers, orders and items';
end;
$$;
reset role;
drop trigger test_checkout_injected_failure on public.order_items;

set local role anon;
do $$
begin
    begin
        perform public.create_order('Denied', 'atomic-denied@example.invalid', null,
            '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":1}]');
        raise exception 'anon unexpectedly executed RPC';
    exception when insufficient_privilege then
        null;
    end;
end;
$$;
reset role;
set local role authenticated;
do $$
begin
    begin
        perform public.create_order('Denied', 'atomic-denied@example.invalid', null,
            '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":1}]');
        raise exception 'authenticated unexpectedly executed RPC';
    exception when insufficient_privilege then
        null;
    end;
end;
$$;
reset role;

-- Temporarily permit invocation but not table access: invoker must not elevate.
savepoint checkout_invoker_test;
grant usage on schema public to anon;
grant execute on function public.create_order(text, text, text, jsonb) to anon;
set local role anon;
do $$
begin
    begin
        perform public.create_order('Denied', 'atomic-denied@example.invalid', null,
            '[{"product_id":"00200000-0000-4000-8000-000000000001","quantity":1}]');
        raise exception 'SECURITY INVOKER unexpectedly bypassed table privileges';
    exception when insufficient_privilege then
        null;
    end;
end;
$$;
reset role;
rollback to savepoint checkout_invoker_test;
release savepoint checkout_invoker_test;

do $$
begin
    perform public._test_checkout_assert(
        not exists (select 1 from public.customers where email = 'atomic-denied@example.invalid'),
        'denied calls write nothing');
    raise notice 'PASS: anon/authenticated denied; invoker cannot bypass table permissions';
end;
$$;

rollback;
