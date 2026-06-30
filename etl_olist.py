import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

CSV_DIR = os.getenv("CSV_DIR", "../brazilian-ecommerce")


def get_connection():
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"),
        port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DATABASE"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    )


def insert_batches(cur, query, data, batch_size=1000, table_name=""):
    """Inserts data in batches and logs progress."""
    total = len(data)
    if total == 0:
        logging.info(f"No data to insert into {table_name}.")
        return

    for i in range(0, total, batch_size):
        batch = data[i:i + batch_size]
        execute_values(cur, query, batch)
        logging.info(f"Inserted {min(i + batch_size, total)}/{total} rows into {table_name}")


def to_val(x):
    """Convert pandas NA / NaN / NaT to None so psycopg2 writes NULL."""
    return None if pd.isnull(x) else x


def run_etl():
    logging.info("Starting Olist ETL process...")

    # ------------------------------------------------------------------ #
    # 1. Load all source CSVs                                             #
    # ------------------------------------------------------------------ #
    logging.info("Reading CSV files...")

    customers_df = pd.read_csv(f"{CSV_DIR}/olist_customers_dataset.csv", dtype=str)

    sellers_df = pd.read_csv(f"{CSV_DIR}/olist_sellers_dataset.csv", dtype=str)

    products_df = pd.read_csv(f"{CSV_DIR}/olist_products_dataset.csv")
    translation_df = pd.read_csv(f"{CSV_DIR}/product_category_name_translation.csv")

    geo_df = pd.read_csv(f"{CSV_DIR}/olist_geolocation_dataset.csv")

    ts_cols_orders = [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    orders_df = pd.read_csv(f"{CSV_DIR}/olist_orders_dataset.csv", parse_dates=ts_cols_orders)

    items_df = pd.read_csv(
        f"{CSV_DIR}/olist_order_items_dataset.csv",
        parse_dates=["shipping_limit_date"]
    )

    payments_df = pd.read_csv(f"{CSV_DIR}/olist_order_payments_dataset.csv")

    reviews_df = pd.read_csv(
        f"{CSV_DIR}/olist_order_reviews_dataset.csv",
        parse_dates=["review_creation_date", "review_answer_timestamp"]
    )

    # ------------------------------------------------------------------ #
    # 2. Transformations                                                  #
    # ------------------------------------------------------------------ #

    # dim_products: fix typos in source column names, join English category
    products_df = products_df.rename(columns={
        "product_name_lenght": "product_name_length",
        "product_description_lenght": "product_description_length",
    })
    products_df = products_df.merge(translation_df, on="product_category_name", how="left")

    # fact_order_items: CSV "order_item_id" is the per-order sequence number, not a PK
    items_df = items_df.rename(columns={"order_item_id": "order_item_sequence"})

    # fact_order_reviews: 814 duplicate review_ids in source — keep latest answer
    before = len(reviews_df)
    reviews_df = reviews_df.sort_values("review_answer_timestamp").drop_duplicates(
        subset="review_id", keep="last"
    )
    logging.info(f"Deduplicated reviews: removed {before - len(reviews_df)} duplicate review_ids")

    conn = get_connection()
    cur = conn.cursor()

    try:
        # -------------------------------------------------------------- #
        # 3. dim_customers                                                #
        # -------------------------------------------------------------- #
        customers_data = [
            (
                row.customer_id,
                row.customer_unique_id,
                to_val(row.customer_zip_code_prefix),
                to_val(row.customer_city),
                to_val(row.customer_state),
            )
            for row in customers_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO dim_customers
                (customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state)
            VALUES %s
            ON CONFLICT (customer_id) DO NOTHING
        """, customers_data, table_name="dim_customers")

        # -------------------------------------------------------------- #
        # 4. dim_sellers                                                  #
        # -------------------------------------------------------------- #
        sellers_data = [
            (
                row.seller_id,
                to_val(row.seller_zip_code_prefix),
                to_val(row.seller_city),
                to_val(row.seller_state),
            )
            for row in sellers_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO dim_sellers
                (seller_id, seller_zip_code_prefix, seller_city, seller_state)
            VALUES %s
            ON CONFLICT (seller_id) DO NOTHING
        """, sellers_data, table_name="dim_sellers")

        # -------------------------------------------------------------- #
        # 5. dim_products                                                 #
        # -------------------------------------------------------------- #
        products_data = [
            (
                row.product_id,
                to_val(row.product_category_name_english),
                to_val(row.product_name_length) if pd.notnull(row.product_name_length) else None,
                to_val(row.product_description_length) if pd.notnull(row.product_description_length) else None,
                int(row.product_photos_qty) if pd.notnull(row.product_photos_qty) else None,
                float(row.product_weight_g) if pd.notnull(row.product_weight_g) else None,
                float(row.product_length_cm) if pd.notnull(row.product_length_cm) else None,
                float(row.product_height_cm) if pd.notnull(row.product_height_cm) else None,
                float(row.product_width_cm) if pd.notnull(row.product_width_cm) else None,
            )
            for row in products_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO dim_products
                (product_id, product_category_name_english, product_name_length,
                 product_description_length, product_photos_qty, product_weight_g,
                 product_length_cm, product_height_cm, product_width_cm)
            VALUES %s
            ON CONFLICT (product_id) DO NOTHING
        """, products_data, table_name="dim_products")

        # -------------------------------------------------------------- #
        # 6. dim_geolocation (SERIAL PK — no natural unique key,         #
        #    plain insert; run script only on empty table or after        #
        #    TRUNCATE dim_geolocation RESTART IDENTITY CASCADE)          #
        # -------------------------------------------------------------- #
        geo_data = [
            (
                to_val(row.geolocation_zip_code_prefix),
                float(row.geolocation_lat) if pd.notnull(row.geolocation_lat) else None,
                float(row.geolocation_lng) if pd.notnull(row.geolocation_lng) else None,
                to_val(row.geolocation_city),
                to_val(row.geolocation_state),
            )
            for row in geo_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO dim_geolocation
                (geolocation_zip_code_prefix, geolocation_lat, geolocation_lng,
                 geolocation_city, geolocation_state)
            VALUES %s
        """, geo_data, table_name="dim_geolocation")

        # -------------------------------------------------------------- #
        # 7. dim_orders                                                   #
        # -------------------------------------------------------------- #
        orders_data = [
            (
                row.order_id,
                row.customer_id,
                to_val(row.order_status),
                to_val(row.order_purchase_timestamp),
                to_val(row.order_approved_at),
                to_val(row.order_delivered_carrier_date),
                to_val(row.order_delivered_customer_date),
                to_val(row.order_estimated_delivery_date),
            )
            for row in orders_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO dim_orders
                (order_id, customer_id, order_status, order_purchase_timestamp,
                 order_approved_at, order_delivered_carrier_date,
                 order_delivered_customer_date, order_estimated_delivery_date)
            VALUES %s
            ON CONFLICT (order_id) DO NOTHING
        """, orders_data, table_name="dim_orders")

        # -------------------------------------------------------------- #
        # 8. fact_order_items (SERIAL PK; natural composite key is       #
        #    order_id + order_item_sequence — add UNIQUE constraint to   #
        #    enable ON CONFLICT on re-runs)                               #
        # -------------------------------------------------------------- #
        items_data = [
            (
                row.order_id,
                int(row.order_item_sequence),
                row.product_id,
                row.seller_id,
                to_val(row.shipping_limit_date),
                float(row.price) if pd.notnull(row.price) else None,
                float(row.freight_value) if pd.notnull(row.freight_value) else None,
            )
            for row in items_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO fact_order_items
                (order_id, order_item_sequence, product_id, seller_id,
                 shipping_limit_date, price, freight_value)
            VALUES %s
        """, items_data, table_name="fact_order_items")

        # -------------------------------------------------------------- #
        # 9. fact_order_payments (SERIAL PK; natural composite key is    #
        #    order_id + payment_sequential)                               #
        # -------------------------------------------------------------- #
        payments_data = [
            (
                row.order_id,
                int(row.payment_sequential),
                to_val(row.payment_type),
                int(row.payment_installments) if pd.notnull(row.payment_installments) else None,
                float(row.payment_value) if pd.notnull(row.payment_value) else None,
            )
            for row in payments_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO fact_order_payments
                (order_id, payment_sequential, payment_type, payment_installments, payment_value)
            VALUES %s
        """, payments_data, table_name="fact_order_payments")

        # -------------------------------------------------------------- #
        # 10. fact_order_reviews                                          #
        # -------------------------------------------------------------- #
        reviews_data = [
            (
                row.review_id,
                row.order_id,
                int(row.review_score) if pd.notnull(row.review_score) else None,
                to_val(row.review_comment_title),
                to_val(row.review_comment_message),
                to_val(row.review_creation_date),
                to_val(row.review_answer_timestamp),
            )
            for row in reviews_df.itertuples(index=False)
        ]
        insert_batches(cur, """
            INSERT INTO fact_order_reviews
                (review_id, order_id, review_score, review_comment_title,
                 review_comment_message, review_creation_date, review_answer_timestamp)
            VALUES %s
            ON CONFLICT (review_id) DO NOTHING
        """, reviews_data, table_name="fact_order_reviews")

        conn.commit()
        logging.info("Olist ETL process completed successfully.")

    except Exception as e:
        conn.rollback()
        logging.error(f"An error occurred: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    run_etl()
