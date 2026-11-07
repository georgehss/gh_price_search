import sqlite3
from pathlib import Path
from contextlib import contextmanager
from src.config import Config

@contextmanager
def get_db():
    """Context manager seguro que garante commits, rollbacks e fechamento da conexão SQLite."""
    Config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_connection() -> sqlite3.Connection:
    """Retorna uma conexão avulsa com SQLite (mantida para compatibilidade)."""
    Config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    """Inicializa o banco de dados com modo WAL e cria as tabelas se não existirem."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Habilita Write-Ahead Logging para concorrência entre threads e Streamlit
        cursor.execute("PRAGMA journal_mode = WAL;")

        # Configurações do sistema (telefone, monitoramento, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        # Produtos monitorados
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monitored_products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL UNIQUE,
                target_price REAL DEFAULT 0.0,
                is_active INTEGER DEFAULT 1,
                current_lowest_price REAL DEFAULT 0.0,
                lowest_store TEXT DEFAULT '',
                lowest_link TEXT DEFAULT '',
                last_checked_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Histórico de preços
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                keyword TEXT NOT NULL,
                price REAL NOT NULL,
                store TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT,
                coupon_code TEXT,
                recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES monitored_products(id) ON DELETE CASCADE
            );
        """)

        # Registro de alertas disparados via CallMeBot
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS alert_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                phone TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Migrações seguras de colunas complementares
        try:
            cursor.execute("ALTER TABLE monitored_products ADD COLUMN last_title TEXT DEFAULT '';")
        except sqlite3.OperationalError:
            pass

    # Sincronização inicial com Google Sheets (caso configurado)
    try:
        from src.database.gsheets_sync import GoogleSheetsSync
        GoogleSheetsSync.pull_to_sqlite()
    except Exception:
        pass
