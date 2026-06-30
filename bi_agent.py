import anthropic
import psycopg2
from psycopg2.extras import RealDictCursor
import os, json
from dotenv import load_dotenv
from tabulate import tabulate

load_dotenv()

client = anthropic.Anthropic()

SCHEMA_DESCRIPTION = """
You have access to the Olist Brazilian E-commerce data warehouse with these tables:

DIMENSIONS:
- dim_customers(customer_id PK, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state)
- dim_sellers(seller_id PK, seller_zip_code_prefix, seller_city, seller_state)
- dim_products(product_id PK, product_category_name_english, product_name_length, product_description_length, product_photos_qty, product_weight_g, product_length_cm, product_height_cm, product_width_cm)
- dim_geolocation(geolocation_id PK, geolocation_zip_code_prefix, geolocation_lat, geolocation_lng, geolocation_city, geolocation_state)
- dim_orders(order_id PK, customer_id FK, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date)

FACTS:
- fact_order_items(order_item_id PK, order_id FK, order_item_sequence, product_id FK, seller_id FK, shipping_limit_date, price, freight_value)
- fact_order_payments(payment_id PK, order_id FK, payment_sequential, payment_type, payment_installments, payment_value)
- fact_order_reviews(review_id PK, order_id FK, review_score 1-5, review_comment_title, review_comment_message, review_creation_date, review_answer_timestamp)

Use run_query to answer the user's business intelligence question with a SELECT query.
"""

TOOLS = [
    {
        "name": "run_query",
        "description": "Execute a SELECT SQL query against the Olist PostgreSQL data warehouse.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "A valid PostgreSQL SELECT statement."}
            },
            "required": ["sql"],
        },
    }
]


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DATABASE"), user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


def run_query(sql: str) -> str:
    if not sql.strip().upper().startswith(("SELECT", "WITH")):
        return "Error: only SELECT queries allowed."
    conn = get_conn()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchmany(200)
            return json.dumps([dict(r) for r in rows], default=str)
    except Exception as e:
        return f"Query error: {e}"


def ask(question: str):
    print(f"\nQuestion: {question}\n")
    messages = [{"role": "user", "content": question}]

    while True:
        response = client.messages.create(
            model="claude-opus-4-8",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=SCHEMA_DESCRIPTION,
            tools=TOOLS,
            messages=messages,
        )

        # Collect any tool calls
        tool_calls = [b for b in response.content if b.type == "tool_use"]

        if not tool_calls:
            # Final answer — find the text block
            for block in response.content:
                if hasattr(block, "text"):
                    print(block.text)
            break

        # Execute each tool call and feed results back
        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for tc in tool_calls:
            sql = tc.input["sql"]
            print(f"[SQL] {sql}\n")
            result = run_query(sql)

            # Pretty-print if it's a JSON array
            try:
                rows = json.loads(result)
                if isinstance(rows, list) and rows:
                    print(tabulate(rows, headers="keys", tablefmt="rounded_outline"))
            except Exception:
                pass

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})


if __name__ == "__main__":
    print("Olist BI Agent — type 'exit' to quit\n")
    while True:
        q = input("Ask a question: ").strip()
        if q.lower() in ("exit", "quit", ""):
            break
        ask(q)
