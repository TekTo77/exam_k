-- Пример пустой схемы для задания «Чудо Обувь». Импорт произвольных Excel
-- не использует этот файл: его таблицы определяются из самих файлов.
BEGIN;
CREATE TABLE IF NOT EXISTS public.roles (
    role_id BIGSERIAL PRIMARY KEY,
    role_name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS public.users (
    user_id BIGSERIAL PRIMARY KEY,
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    login TEXT NOT NULL UNIQUE,
    role_id BIGINT NOT NULL REFERENCES public.roles(role_id)
);
CREATE TABLE IF NOT EXISTS public.products (
    product_id BIGSERIAL PRIMARY KEY,
    category TEXT,
    subcategory TEXT,
    product_name TEXT NOT NULL,
    manufacturer TEXT,
    image_path TEXT,
    composition TEXT,
    description TEXT,
    price NUMERIC(12,2) NOT NULL CHECK (price >= 0)
);
CREATE TABLE IF NOT EXISTS public.sizes (
    size_id BIGSERIAL PRIMARY KEY,
    size_value NUMERIC(6,2) NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS public.stock_items (
    stock_item_id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES public.products(product_id),
    size_id BIGINT NOT NULL REFERENCES public.sizes(size_id),
    quantity_available INTEGER NOT NULL CHECK (quantity_available >= 0),
    UNIQUE (product_id, size_id)
);
CREATE TABLE IF NOT EXISTS public.orders (
    order_id BIGSERIAL PRIMARY KEY,
    order_date DATE NOT NULL,
    user_id BIGINT NOT NULL REFERENCES public.users(user_id)
);
CREATE TABLE IF NOT EXISTS public.order_items (
    order_item_id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES public.orders(order_id),
    product_id BIGINT NOT NULL REFERENCES public.products(product_id),
    size_id BIGINT NOT NULL REFERENCES public.sizes(size_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12,2) NOT NULL CHECK (unit_price >= 0),
    UNIQUE (order_id, product_id, size_id)
);
COMMIT;
