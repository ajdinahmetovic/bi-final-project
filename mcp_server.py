from mcp.server.fastmcp import FastMCP
import psycopg2
from psycopg2.extras import RealDictCursor
import os, json
from dotenv import load_dotenv

load_dotenv()

mcp = FastMCP("Olist BI Server")

TABLES = [
    "dim_customers", "dim_sellers", "dim_products", "dim_geolocation",
    "dim_orders", "fact_order_items", "fact_order_payments", "fact_order_reviews",
]


def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST"), port=os.getenv("POSTGRES_PORT"),
        database=os.getenv("POSTGRES_DATABASE"), user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
    )


@mcp.tool()
def list_tables() -> list[str]:
    """List all tables in the Olist data warehouse."""
    return TABLES


@mcp.tool()
def get_table_schema(table_name: str) -> str:
    """Get column names and types for a table."""
    conn = get_conn()
    with conn, conn.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        rows = cur.fetchall()
    return "\n".join(f"  {col}: {dtype}" for col, dtype in rows)


@mcp.tool()
def run_query(sql: str) -> str:
    """Execute a SELECT query and return results as JSON (max 200 rows)."""
    if not sql.strip().upper().startswith(("SELECT", "WITH")):
        return "Error: only SELECT queries allowed."
    conn = get_conn()
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = cur.fetchmany(200)
            return json.dumps([dict(r) for r in rows], default=str, indent=2)
    except Exception as e:
        return f"Query error: {e}"


if __name__ == "__main__":
    mcp.run()
