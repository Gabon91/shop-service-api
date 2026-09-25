-- Apply after 001_initial_schema.sql as the migration owner (PostgreSQL 13+).
begin;

create function public.create_order(
    p_customer_name text,
    p_customer_email text,
    p_customer_phone text,
    p_items jsonb
)
returns jsonb
language plpgsql
security invoker
set search_path = pg_catalog
set extra_float_digits = 3
as $function$
declare
    v_item jsonb;
    v_product_id uuid;
    v_quantity_text text;
    v_product_ids uuid[] := array[]::uuid[];
    v_quantities integer[] := array[]::integer[];
    v_prices double precision[];
    v_product record;
    v_index integer;
    v_found integer := 0;
    v_total numeric := 0;
    v_stored_total double precision;
    v_customer public.customers%rowtype;
    v_order public.orders%rowtype;
    v_items jsonb;
begin
    if p_customer_name is null or p_customer_name !~ '[^[:space:]]'
       or p_customer_email is null or p_customer_email !~ '[^[:space:]]' then
        raise exception using errcode = 'PT400', message = 'Customer name and email must not be blank';
    end if;

    if p_items is null or jsonb_typeof(p_items) is distinct from 'array' then
        raise exception using errcode = 'PT400', message = 'Items must be a nonempty JSON array';
    end if;
    if jsonb_array_length(p_items) = 0 then
        raise exception using errcode = 'PT400', message = 'Items must be a nonempty JSON array';
    end if;

    for v_item in select value from jsonb_array_elements(p_items)
    loop
        if jsonb_typeof(v_item) is distinct from 'object'
           or jsonb_typeof(v_item -> 'product_id') is distinct from 'string'
           or jsonb_typeof(v_item -> 'quantity') is distinct from 'number' then
            raise exception using errcode = 'PT400', message = 'Each item requires a UUID product_id and integer quantity';
        end if;

        begin
            v_product_id := (v_item ->> 'product_id')::uuid;
        exception when invalid_text_representation then
            raise exception using errcode = 'PT400', message = 'Invalid product UUID';
        end;

        -- Validate the JSONB numeric representation, never coerce strings or round decimals.
        v_quantity_text := v_item ->> 'quantity';
        if v_quantity_text !~ '^[1-9][0-9]*$' or length(v_quantity_text) > 10 then
            raise exception using errcode = 'PT400', message = 'Quantity must be a positive 32-bit JSON integer';
        end if;
        if v_quantity_text::numeric > 2147483647 then
            raise exception using errcode = 'PT400', message = 'Quantity exceeds the 32-bit integer limit';
        end if;
        if v_product_id = any(v_product_ids) then
            raise exception using errcode = 'PT409', message = 'Duplicate product in items';
        end if;
        v_product_ids := array_append(v_product_ids, v_product_id);
        v_quantities := array_append(v_quantities, v_quantity_text::integer);
    end loop;

    v_prices := array_fill(0::double precision, array[cardinality(v_product_ids)]);
    -- UUID ordering prevents lock-order inversions. SHARE allows concurrent checkouts
    -- while blocking catalog price updates/deletes until the caller's transaction ends.
    for v_product in
        select p.id, p.price
        from public.products as p
        where p.id = any(v_product_ids)
        order by p.id
        for share of p
    loop
        v_found := v_found + 1;
        v_index := array_position(v_product_ids, v_product.id);
        v_prices[v_index] := v_product.price;
        -- Round-trip float text and decimal arithmetic avoid accumulating binary
        -- line totals; extra_float_digits above makes this independent of the caller.
        v_total := v_total + v_product.price::text::numeric * v_quantities[v_index];
    end loop;

    if v_found <> cardinality(v_product_ids) then
        raise exception using errcode = 'PT404', message = 'Product not found';
    end if;
    begin
        v_stored_total := v_total::double precision;
    exception when numeric_value_out_of_range then
        raise exception using errcode = 'PT400', message = 'Order total exceeds finite double precision storage';
    end;
    if not (v_stored_total >= 0 and v_stored_total < 'Infinity'::double precision) then
        raise exception using errcode = 'PT400', message = 'Order total exceeds finite double precision storage';
    end if;

    -- Email is used verbatim: identity remains case-sensitive, matching the unique key.
    -- A null phone preserves the existing phone; a non-null phone replaces it.
    insert into public.customers as existing (name, email, phone)
    values (p_customer_name, p_customer_email, p_customer_phone)
    on conflict (email) do update
        set name = excluded.name,
            phone = coalesce(excluded.phone, existing.phone)
    returning * into v_customer;

    insert into public.orders (customer_id, total_amount)
    values (v_customer.id, v_stored_total)
    returning * into v_order;

    -- Stock is informational: checkout neither enforces nor decrements it.
    with inserted as (
        insert into public.order_items (order_id, product_id, quantity, price)
        select v_order.id, v_product_ids[i], v_quantities[i], v_prices[i]
        from generate_subscripts(v_product_ids, 1) as indices(i)
        returning *
    )
    select jsonb_agg(to_jsonb(inserted) order by array_position(v_product_ids, inserted.product_id))
    into v_items
    from inserted;

    return to_jsonb(v_order) || jsonb_build_object('customer', to_jsonb(v_customer), 'items', v_items);
end;
$function$;

revoke all on function public.create_order(text, text, text, jsonb) from public, anon, authenticated;
grant execute on function public.create_order(text, text, text, jsonb) to service_role;

notify pgrst, 'reload schema';
commit;
