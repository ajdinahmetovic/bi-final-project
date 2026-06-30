# Olist BI Agent

An end-to-end Business Intelligence pipeline on the [Olist Brazilian E-commerce dataset](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

Ask questions in plain English → get SQL-generated answers from a real data warehouse.

## Stack
- **PostgreSQL** (Supabase) — star schema data warehouse
- **Python** — ETL, MCP server, BI agent
- **Claude claude-opus-4-8** — natural language to SQL
- **Apache Superset** — dashboards

## Setup

```bash
pip3 install -r requirements.txt
cp .env.example .env   # fill in your credentials
```

## Usage

**1. Load data (run once)**
```bash
python3 etl_olist.py
```

**2. Ask business questions**
```bash
python3 bi_agent.py
```

**3. Dashboards**
```bash
docker compose up -d
# open http://localhost:8088  (admin / admin)
```

## Project Structure
```
├── etl_olist.py        # ETL: CSV → Supabase star schema
├── mcp_server.py       # MCP server exposing DB tools
├── bi_agent.py         # BI agent (natural language → SQL)
├── Dockerfile          # Superset + psycopg2
├── docker-compose.yml  # Superset deployment
└── PROJECT_DOCUMENTATION.md
```
