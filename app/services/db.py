import os
import json
import asyncio
from datetime import datetime
import psycopg
from psycopg.rows import dict_row

# Fetch database URL from environment variable
# Defaulting to Transaction Pooler (port 6543) for better cloud compatibility
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.hbnjzmkbkcpsyrppspsb:[YOUR-PASSWORD]@aws-1-us-west-2.pooler.supabase.com:6543/postgres")

async def get_db_connection():
    # Helper to get a connection with dict_row factory
    # Masking password for security in logs
    import re
    username = "unknown"
    host_part = "unknown"
    match = re.search(r"postgresql://([^:]+):[^@]+@(.+)", DATABASE_URL)
    if match:
        username = match.group(1)
        host_part = match.group(2)
    
    print(f"DEBUG: Tentando conectar como usuário '{username}' no host '{host_part}'")
    return await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row)

async def init_db():
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    payment_id TEXT,
                    cnpj TEXT,
                    razao_social TEXT,
                    plan TEXT,
                    price REAL,
                    status TEXT,
                    phone TEXT,
                    gov_password TEXT,
                    progress INTEGER DEFAULT 0,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Migration check: Add columns if they don't exist
            try:
                await cur.execute("ALTER TABLE leads ADD COLUMN IF NOT EXISTS razao_social TEXT")
            except:
                pass
            await conn.commit()

async def save_order(order_data: dict):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                INSERT INTO leads (id, payment_id, cnpj, razao_social, plan, price, status, progress, message)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                order_data["id"],
                order_data["payment_id"],
                order_data["cnpj"],
                order_data.get("razao_social", ""),
                order_data["plan"],
                order_data["price"],
                order_data["status"],
                order_data.get("progress", 0),
                order_data.get("message", "")
            ))
            await conn.commit()

async def get_order(order_id: str):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM leads WHERE id = %s", (order_id,))
            return await cur.fetchone()

async def update_order_status(order_id: str, status: str, progress: int, message: str):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE leads 
                SET status = %s, progress = %s, message = %s
                WHERE id = %s
            """, (status, progress, message, order_id))
            await conn.commit()

async def update_payment_paid(order_id: str):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE leads 
                SET status = 'paid', message = 'Pagamento aprovado!'
                WHERE id = %s
            """, (order_id,))
            await conn.commit()

async def update_contact_phone(order_id: str, phone: str):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE leads SET phone = %s WHERE id = %s
            """, (phone, order_id))
            await conn.commit()

async def update_gov_password(order_id: str, password: str):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("""
                UPDATE leads SET gov_password = %s WHERE id = %s
            """, (password, order_id))
            await conn.commit()

async def get_all_leads():
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT * FROM leads ORDER BY created_at DESC")
            return await cur.fetchall()

async def delete_lead(order_id: str):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("DELETE FROM leads WHERE id = %s", (order_id,))
            await conn.commit()

async def get_lead_for_tracking(cnpj: str, phone_suffix: str):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            query = "SELECT * FROM leads WHERE cnpj = %s AND status IN ('paid', 'completed')"
            await cur.execute(query, (cnpj,))
            rows = await cur.fetchall()
            for row in rows:
                if row['phone'] and row['phone'].replace('-', '').replace(' ', '').replace('(', '').replace(')', '').endswith(phone_suffix):
                    return row
            return None

async def update_lead_contact(order_id: str, phone: str, name: str = None):
    async with await get_db_connection() as conn:
        async with conn.cursor() as cur:
            if name:
                await cur.execute("UPDATE leads SET phone = %s, razao_social = %s WHERE id = %s", (phone, name, order_id))
            else:
                await cur.execute("UPDATE leads SET phone = %s WHERE id = %s", (phone, order_id))
            await conn.commit()
