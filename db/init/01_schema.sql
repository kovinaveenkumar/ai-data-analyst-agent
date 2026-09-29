-- =====================================================================
-- E-commerce analytics schema (PostgreSQL 16)
-- Every table and column carries a COMMENT: the MCP server reads these
-- and hands them to Claude as the data dictionary.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS shop;
SET search_path TO shop;

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    full_name     TEXT        NOT NULL,
    email         TEXT,
    city          TEXT        NOT NULL,
    state         CHAR(2)     NOT NULL,
    segment       TEXT        NOT NULL CHECK (segment IN ('Consumer','Small Business','Corporate')),
    signup_date   DATE        NOT NULL
);
COMMENT ON TABLE  customers IS 'One row per registered customer.';
COMMENT ON COLUMN customers.email IS 'Contact email. Can be NULL (known data-quality gap).';
COMMENT ON COLUMN customers.state IS 'US state, two-letter code.';
COMMENT ON COLUMN customers.segment IS 'Customer type: Consumer, Small Business or Corporate.';
COMMENT ON COLUMN customers.signup_date IS 'Date the customer created an account.';

CREATE TABLE categories (
    category_id   INTEGER PRIMARY KEY,
    category_name TEXT NOT NULL UNIQUE
);
COMMENT ON TABLE categories IS 'Product categories (8 in total).';

CREATE TABLE products (
    product_id    INTEGER PRIMARY KEY,
    product_name  TEXT          NOT NULL,
    category_id   INTEGER       NOT NULL REFERENCES categories(category_id),
    list_price    NUMERIC(10,2) NOT NULL CHECK (list_price > 0),
    unit_cost     NUMERIC(10,2) NOT NULL CHECK (unit_cost > 0),
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE
);
COMMENT ON TABLE  products IS 'Product catalogue.';
COMMENT ON COLUMN products.list_price IS 'Current selling price in USD.';
COMMENT ON COLUMN products.unit_cost IS 'What one unit costs the company in USD. Profit = revenue - quantity * unit_cost.';

CREATE TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date    DATE    NOT NULL,
    status        TEXT    NOT NULL CHECK (status IN ('processing','shipped','delivered','cancelled')),
    channel       TEXT    NOT NULL CHECK (channel IN ('web','mobile','marketplace'))
);
COMMENT ON TABLE  orders IS 'One row per order. Orders run from 2024-01-01 to 2025-12-31.';
COMMENT ON COLUMN orders.status IS 'processing, shipped, delivered or cancelled. Revenue EXCLUDES cancelled orders.';
COMMENT ON COLUMN orders.channel IS 'Where the order was placed: web, mobile or marketplace.';

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id      INTEGER       NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER       NOT NULL REFERENCES products(product_id),
    quantity      INTEGER       NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(10,2) NOT NULL,
    discount      NUMERIC(4,2)  NOT NULL DEFAULT 0 CHECK (discount >= 0 AND discount < 1),
    line_total    NUMERIC(12,2) GENERATED ALWAYS AS (ROUND(quantity * unit_price * (1 - discount), 2)) STORED
);
COMMENT ON TABLE  order_items IS 'Line items of each order.';
COMMENT ON COLUMN order_items.unit_price IS 'Price per unit at the time of the order (USD).';
COMMENT ON COLUMN order_items.discount IS 'Discount as a fraction, e.g. 0.10 = 10% off.';
COMMENT ON COLUMN order_items.line_total IS 'Revenue of the line in USD = quantity * unit_price * (1 - discount). Sum this for revenue.';

CREATE TABLE returns (
    return_id     INTEGER PRIMARY KEY,
    order_item_id INTEGER       NOT NULL REFERENCES order_items(order_item_id),
    return_date   DATE          NOT NULL,
    reason        TEXT          NOT NULL,
    refund_amount NUMERIC(12,2) NOT NULL
);
COMMENT ON TABLE  returns IS 'Returned order lines and the refund paid.';
COMMENT ON COLUMN returns.reason IS 'damaged, wrong item, not as described, changed mind or late delivery.';

CREATE INDEX ON orders (order_date);
CREATE INDEX ON orders (customer_id);
CREATE INDEX ON order_items (order_id);
CREATE INDEX ON order_items (product_id);
