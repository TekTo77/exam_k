-- Только отношения. Пропущенные таблицы/колонки не создаются.
-- Для своих Excel поменяй строки списка или используй SQL из редактора.
BEGIN;
DO $$
DECLARE
    item RECORD;
    target_schema TEXT := current_schema();
    child_oid OID;
    parent_oid OID;
    child_number SMALLINT;
    parent_number SMALLINT;
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('users', 'role_id', 'roles', 'role_id', 'fk_users_role_id'),
        ('subcategories', 'category_id', 'categories', 'category_id', 'fk_subcategories_category_id'),
        ('products', 'subcategory_id', 'subcategories', 'subcategory_id', 'fk_products_subcategory_id'),
        ('products', 'manufacturer_id', 'manufacturers', 'manufacturer_id', 'fk_products_manufacturer_id'),
        ('stock_items', 'product_id', 'products', 'product_id', 'fk_stock_items_product_id'),
        ('stock_items', 'size_id', 'sizes', 'size_id', 'fk_stock_items_size_id'),
        ('orders', 'user_id', 'users', 'user_id', 'fk_orders_user_id'),
        ('order_items', 'order_id', 'orders', 'order_id', 'fk_order_items_order_id'),
        ('order_items', 'product_id', 'products', 'product_id', 'fk_order_items_product_id'),
        ('order_items', 'size_id', 'sizes', 'size_id', 'fk_order_items_size_id')
    ) AS links(child_table, child_column, parent_table, parent_column, constraint_name)
    LOOP
        child_oid := to_regclass(format('%I.%I', target_schema, item.child_table));
        parent_oid := to_regclass(format('%I.%I', target_schema, item.parent_table));
        SELECT attnum INTO child_number FROM pg_attribute
            WHERE attrelid = child_oid AND attname = item.child_column AND NOT attisdropped;
        SELECT attnum INTO parent_number FROM pg_attribute
            WHERE attrelid = parent_oid AND attname = item.parent_column AND NOT attisdropped;
        IF child_number IS NULL OR parent_number IS NULL THEN
            RAISE NOTICE 'Пропущено %.% -> %.%: нет таблицы или колонки',
                item.child_table, item.child_column, item.parent_table, item.parent_column;
            CONTINUE;
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE contype = 'f' AND conrelid = child_oid AND confrelid = parent_oid
              AND conkey = ARRAY[child_number] AND confkey = ARRAY[parent_number]
        ) THEN
            EXECUTE format('ALTER TABLE %I.%I ADD CONSTRAINT %I FOREIGN KEY (%I) REFERENCES %I.%I (%I)',
                target_schema, item.child_table, item.constraint_name, item.child_column,
                target_schema, item.parent_table, item.parent_column);
        END IF;
    END LOOP;
END $$;
COMMIT;
