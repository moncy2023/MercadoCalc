# Python 3.10+
import sqlite3
import os

DB_PATH = "shipping_fees.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    countries = ["Mexico", "Brazil", "Chile", "Argentina", "Colombia"]
    for country in countries:
        table_name = f"shipping_{country}"
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                weight_min REAL,
                weight_max REAL,
                fee_below REAL,
                fee_above REAL
            )
        """)
    # 国家元数据：免邮阈值、本币名称、本币对USD汇率
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS country_metadata (
            country TEXT PRIMARY KEY,
            local_currency TEXT,
            threshold_local REAL,
            threshold_usd REAL
        )
    """)
    conn.commit()
    conn.close()

def set_country_metadata(country, local_currency, threshold_local, threshold_usd):
    """设置某国家的免邮阈值等元信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS country_metadata (
            country TEXT PRIMARY KEY,
            local_currency TEXT,
            threshold_local REAL,
            threshold_usd REAL
        )
    """)
    cursor.execute("""
        INSERT OR REPLACE INTO country_metadata (country, local_currency, threshold_local, threshold_usd)
        VALUES (?, ?, ?, ?)
    """, (country, local_currency, threshold_local, threshold_usd))
    conn.commit()
    conn.close()

def get_country_metadata(country):
    """获取某国家的免邮阈值等元信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT local_currency, threshold_local, threshold_usd FROM country_metadata WHERE country = ?", (country,))
        result = cursor.fetchone()
    except sqlite3.OperationalError:
        result = None
    conn.close()
    if result:
        return {"local_currency": result[0], "threshold_local": result[1], "threshold_usd": result[2]}
    return None

def insert_rate(country, weight_min, weight_max, fee_below, fee_above):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    table_name = f"shipping_{country}"
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            weight_min REAL,
            weight_max REAL,
            fee_below REAL,
            fee_above REAL
        )
    """)
    cursor.execute(f"""
        INSERT INTO {table_name} (weight_min, weight_max, fee_below, fee_above)
        VALUES (?, ?, ?, ?)
    """, (weight_min, weight_max, fee_below, fee_above))
    conn.commit()
    conn.close()

def get_shipping_fee(country, weight, is_above_threshold=True):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    table_name = f"shipping_{country}"
    fee_column = "fee_above" if is_above_threshold else "fee_below"
    try:
        cursor.execute(f"""
            SELECT {fee_column} FROM {table_name}
            WHERE ? > weight_min AND ? <= weight_max
            ORDER BY {fee_column} ASC LIMIT 1
        """, (weight, weight))
        result = cursor.fetchone()
    except sqlite3.OperationalError:
        result = None
    conn.close()
    if result:
        return result[0]
    return None

def get_country_rates(country):
    """获取某个国家的全部运费阶梯数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    table_name = f"shipping_{country}"
    try:
        cursor.execute(f"""
            SELECT weight_min, weight_max, fee_below, fee_above
            FROM {table_name}
            ORDER BY weight_min ASC
        """)
        results = cursor.fetchall()
    except sqlite3.OperationalError:
        results = []
    conn.close()
    return [
        {"weight_min": r[0], "weight_max": r[1], "fee_below": r[2], "fee_above": r[3]}
        for r in results
    ]

def get_all_countries():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'shipping_%'")
    results = cursor.fetchall()
    conn.close()
    if results:
        return [row[0].replace('shipping_', '') for row in results]
    return ["Mexico", "Brazil", "Chile", "Argentina", "Colombia"]

if __name__ == "__main__":
    init_db()
