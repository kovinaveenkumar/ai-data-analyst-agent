-- =====================================================================
-- Deterministic synthetic data (setseed makes every fresh DB identical).
-- ~2,000 customers, 120 products, ~27,000 orders, ~67,000 order lines.
-- Built-in patterns for the agent to discover: year-over-year growth,
-- a Nov/Dec holiday peak, channel mix shift toward mobile, and a few
-- deliberate data-quality issues (NULL emails, duplicate emails).
-- =====================================================================
SET search_path TO shop;
SELECT setseed(0.42);

-- ---------- categories ----------
INSERT INTO categories VALUES
 (1,'Electronics'),(2,'Home & Kitchen'),(3,'Clothing'),(4,'Sports & Outdoors'),
 (5,'Beauty'),(6,'Books'),(7,'Toys & Games'),(8,'Office Supplies');

-- ---------- customers ----------
INSERT INTO customers
SELECT g,
       (ARRAY['Ava','Liam','Noah','Emma','Olivia','Mia','Ethan','Lucas','Aria','Maya','Arjun','Priya','Diego','Sofia','Chen','Hana','Omar','Zara','Leo','Nina'])[1 + floor(random()*20)::int]
       || ' ' ||
       (ARRAY['Smith','Johnson','Patel','Garcia','Kim','Nguyen','Brown','Davis','Lopez','Wilson','Khan','Reddy','Martin','Lee','Clark','Young','Hall','Allen','King','Scott'])[1 + floor(random()*20)::int],
       CASE WHEN random() < 0.012 THEN NULL ELSE 'customer' || g || '@example.com' END,
       c.city, c.state,
       CASE WHEN r.x < 0.62 THEN 'Consumer' WHEN r.x < 0.87 THEN 'Small Business' ELSE 'Corporate' END,
       DATE '2022-01-01' + floor(random()*730)::int
FROM generate_series(1,2000) g
CROSS JOIN LATERAL (SELECT random() AS x, g AS gg) r
CROSS JOIN LATERAL (
    SELECT (ARRAY['New York','Los Angeles','Chicago','Houston','Phoenix','Seattle','Miami','Denver','Boston','Atlanta','Columbia','Austin','Newark','St. Louis','Kansas City'])[i] AS city,
           (ARRAY['NY','CA','IL','TX','AZ','WA','FL','CO','MA','GA','MO','TX','NJ','MO','MO'])[i] AS state
    FROM (SELECT 1 + floor(random()*15)::int + 0*r.gg AS i) q
) c;

-- a few duplicate emails (data-quality issue for the checker to find)
UPDATE customers SET email = 'customer' || (customer_id - 1) || '@example.com'
WHERE customer_id IN (101, 602, 1403) ;

-- ---------- products ----------
INSERT INTO products
SELECT g,
       (ARRAY['Pro','Classic','Eco','Ultra','Smart','Essential','Premium','Compact'])[1 + floor(random()*8)::int] || ' ' ||
       (CASE cat
          WHEN 1 THEN (ARRAY['Headphones','Charger','Speaker','Webcam','Keyboard'])[1 + floor(random()*5)::int]
          WHEN 2 THEN (ARRAY['Blender','Pan Set','Kettle','Knife Set','Storage Box'])[1 + floor(random()*5)::int]
          WHEN 3 THEN (ARRAY['Jacket','Hoodie','T-Shirt','Jeans','Sneakers'])[1 + floor(random()*5)::int]
          WHEN 4 THEN (ARRAY['Yoga Mat','Water Bottle','Tent','Backpack','Dumbbells'])[1 + floor(random()*5)::int]
          WHEN 5 THEN (ARRAY['Serum','Moisturizer','Shampoo','Perfume','Face Mask'])[1 + floor(random()*5)::int]
          WHEN 6 THEN (ARRAY['Novel','Cookbook','Biography','Guidebook','Workbook'])[1 + floor(random()*5)::int]
          WHEN 7 THEN (ARRAY['Puzzle','Board Game','Building Set','Plush Toy','Card Game'])[1 + floor(random()*5)::int]
          ELSE        (ARRAY['Notebook','Pen Set','Desk Lamp','Organizer','Stapler'])[1 + floor(random()*5)::int]
        END) || ' ' || g,
       cat,
       p.price,
       ROUND(p.price * (0.45 + random()*0.25)::numeric, 2),
       random() > 0.05
FROM generate_series(1,120) g
CROSS JOIN LATERAL (SELECT 1 + ((g - 1) % 8) AS cat) c
CROSS JOIN LATERAL (
    SELECT ROUND((CASE c.cat WHEN 1 THEN 40 + random()*260 WHEN 2 THEN 20 + random()*150
                             WHEN 3 THEN 15 + random()*120 WHEN 4 THEN 15 + random()*200
                             WHEN 5 THEN 8 + random()*60   WHEN 6 THEN 8 + random()*35
                             WHEN 7 THEN 10 + random()*80  ELSE 5 + random()*60 END)::numeric, 2) AS price
) p;

-- ---------- orders ----------
-- base orders with growth (sqrt skews dates later) + an extra holiday wave in Nov/Dec
CREATE TEMP TABLE tmp_order_dates AS
SELECT DATE '2024-01-01' + floor((CASE WHEN random() < 0.5 THEN random() ELSE sqrt(random()) END) * 731)::int AS d FROM generate_series(1,23000)
UNION ALL
SELECT make_date(y, m, 1 + floor(random()*28)::int)
FROM generate_series(1,4000) g
CROSS JOIN LATERAL (SELECT CASE WHEN random() < 0.45 THEN 2024 ELSE 2025 END AS y,
                           CASE WHEN random() < 0.45 THEN 11 ELSE 12 END AS m, g AS gg) x;

-- status and channel use independent hash-based draws (consecutive random() calls correlate)
CREATE TEMP TABLE tmp_orders AS
SELECT row_number() OVER (ORDER BY d, random())::int AS order_id, d FROM tmp_order_dates;

INSERT INTO orders
SELECT t.order_id,
       1 + floor(random()*2000)::int,
       t.d,
       CASE WHEN t.d > DATE '2025-12-24' AND h.s < 0.60 THEN 'processing'
            WHEN t.d > DATE '2025-12-15' AND h.s < 0.50 THEN 'shipped'
            WHEN h.s2 < 0.06 THEN 'cancelled'
            ELSE 'delivered' END,
       -- mobile share grows over time
       CASE WHEN h.c < 0.10 THEN 'marketplace'
            WHEN h.c < 0.10 + 0.25 + 0.25 * ((t.d - DATE '2024-01-01') / 731.0) THEN 'mobile'
            ELSE 'web' END
FROM tmp_orders t
CROSS JOIN LATERAL (SELECT (abs(hashtext('status' || t.order_id)) % 100000) / 100000.0 AS s,
                           (abs(hashtext('cancel' || t.order_id)) % 100000) / 100000.0 AS s2,
                           (abs(hashtext('channel' || t.order_id)) % 100000) / 100000.0 AS c) h;

-- ---------- order items ----------
INSERT INTO order_items (order_item_id, order_id, product_id, quantity, unit_price, discount)
SELECT row_number() OVER (ORDER BY o.order_id, k),
       o.order_id,
       p.product_id,
       1 + floor(random()*3)::int,
       p.list_price,
       CASE WHEN random() < 0.70 THEN 0 WHEN random() < 0.70 THEN 0.10 ELSE 0.20 END
FROM orders o
CROSS JOIN LATERAL generate_series(1, 1 + floor(random()*4)::int + 0*o.order_id) k
CROSS JOIN LATERAL (SELECT 1 + floor(random()*120)::int + 0*k AS pid) pick
JOIN products p ON p.product_id = pick.pid;

-- ---------- returns (~4% of delivered lines) ----------
INSERT INTO returns
SELECT row_number() OVER (ORDER BY oi.order_item_id),
       oi.order_item_id,
       o.order_date + 3 + floor(random()*25)::int,
       (ARRAY['damaged','wrong item','not as described','changed mind','late delivery'])[1 + floor(random()*5)::int],
       oi.line_total
FROM order_items oi JOIN orders o USING (order_id)
WHERE o.status = 'delivered' AND random() < 0.04;

ANALYZE;
