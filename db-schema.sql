-- DIMENSIONS

CREATE TABLE dim_customers (
    customer_id VARCHAR PRIMARY KEY,
    customer_unique_id VARCHAR NOT NULL,
    customer_zip_code_prefix VARCHAR,
    customer_city VARCHAR,
    customer_state VARCHAR(2)
);

CREATE TABLE dim_sellers (
    seller_id VARCHAR PRIMARY KEY,
    seller_zip_code_prefix VARCHAR,
    seller_city VARCHAR,
    seller_state VARCHAR(2)
);

CREATE TABLE dim_products (
    product_id VARCHAR PRIMARY KEY,
    product_category_name_english VARCHAR,
    product_name_length INTEGER,
    product_description_length INTEGER,
    product_photos_qty INTEGER,
    product_weight_g NUMERIC,
    product_length_cm NUMERIC,
    product_height_cm NUMERIC,
    product_width_cm NUMERIC
);

CREATE TABLE dim_geolocation (
    geolocation_id SERIAL PRIMARY KEY,
    geolocation_zip_code_prefix VARCHAR,
    geolocation_lat NUMERIC,
    geolocation_lng NUMERIC,
    geolocation_city VARCHAR,
    geolocation_state VARCHAR(2)
);

CREATE TABLE dim_orders (
    order_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR NOT NULL REFERENCES dim_customers(customer_id),
    order_status VARCHAR,
    order_purchase_timestamp TIMESTAMP,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
);

-- FACT TABLES

CREATE TABLE fact_order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id VARCHAR NOT NULL REFERENCES dim_orders(order_id),
    order_item_sequence INTEGER,
    product_id VARCHAR NOT NULL REFERENCES dim_products(product_id),
    seller_id VARCHAR NOT NULL REFERENCES dim_sellers(seller_id),
    shipping_limit_date TIMESTAMP,
    price NUMERIC(10,2),
    freight_value NUMERIC(10,2)
);

CREATE TABLE fact_order_payments (
    payment_id SERIAL PRIMARY KEY,
    order_id VARCHAR NOT NULL REFERENCES dim_orders(order_id),
    payment_sequential INTEGER,
    payment_type VARCHAR,
    payment_installments INTEGER,
    payment_value NUMERIC(10,2)
);

CREATE TABLE fact_order_reviews (
    review_id VARCHAR PRIMARY KEY,
    order_id VARCHAR NOT NULL REFERENCES dim_orders(order_id),
    review_score INTEGER CHECK (review_score BETWEEN 1 AND 5),
    review_comment_title VARCHAR,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP,
    review_answer_timestamp TIMESTAMP
);