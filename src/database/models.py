import json
import sqlite3
import threading
from typing import List, Dict, Optional, Any
from datetime import datetime
from src.database.db import get_db

def _async_sync_products():
    """Sincroniza os produtos monitorados com o Google Sheets em segundo plano."""
    def _run():
        try:
            from src.database.gsheets_sync import GoogleSheetsSync
            GoogleSheetsSync.sync_monitored_products()
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

def _async_append_price(product_id: Optional[int], keyword: str, price: float, store: str, title: str, link: str, coupon_code: str = ""):
    """Registra uma linha no histórico do Google Sheets em segundo plano."""
    def _run():
        try:
            from src.database.gsheets_sync import GoogleSheetsSync
            GoogleSheetsSync.append_price_record(product_id, keyword, price, store, title, link, coupon_code)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

class DatabaseManager:
    # --- Configurações ---
    @staticmethod
    def get_setting(key: str, default: str = "") -> str:
        with get_db() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    @staticmethod
    def set_setting(key: str, value: str):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value)
            )

    # --- Produtos Monitorados ---
    @staticmethod
    def add_monitored_product(keyword: str, target_price: float = 0.0) -> int:
        clean_kw = keyword.strip()
        with get_db() as conn:
            conn.execute(
                "INSERT INTO monitored_products (keyword, target_price, is_active) VALUES (?, ?, 1) "
                "ON CONFLICT(keyword) DO UPDATE SET target_price = excluded.target_price, is_active = 1",
                (clean_kw, float(target_price))
            )
            row = conn.execute("SELECT id FROM monitored_products WHERE keyword = ?", (clean_kw,)).fetchone()
            _async_sync_products()
            return row["id"] if row else 0

    @staticmethod
    def update_target_price(product_id: int, target_price: float):
        with get_db() as conn:
            conn.execute(
                "UPDATE monitored_products SET target_price = ? WHERE id = ?",
                (float(target_price), product_id)
            )
            _async_sync_products()

    @staticmethod
    def get_monitored_products(active_only: bool = False) -> List[Dict[str, Any]]:
        with get_db() as conn:
            query = "SELECT * FROM monitored_products"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY created_at DESC"
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def toggle_product_active(product_id: int, is_active: bool):
        with get_db() as conn:
            conn.execute(
                "UPDATE monitored_products SET is_active = ? WHERE id = ?",
                (1 if is_active else 0, product_id)
            )
            _async_sync_products()

    @staticmethod
    def delete_monitored_product(product_id: int):
        with get_db() as conn:
            conn.execute("DELETE FROM price_history WHERE product_id = ?", (product_id,))
            conn.execute("DELETE FROM monitored_products WHERE id = ?", (product_id,))
            _async_sync_products()

    @staticmethod
    def update_product_lowest(
        product_id: int,
        lowest_price: float,
        store: str,
        link: str,
        title: str = "",
        scan_snapshot: Optional[Dict[str, Any]] = None,
    ):
        """Atualiza o menor preço atual, metadados da oferta e snapshot JSON da última varredura."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scan_json = json.dumps(scan_snapshot, ensure_ascii=False) if scan_snapshot is not None else None
        with get_db() as conn:
            try:
                if scan_json is not None:
                    conn.execute(
                        "UPDATE monitored_products SET current_lowest_price = ?, lowest_store = ?, lowest_link = ?, last_title = ?, last_scan_json = ?, last_checked_at = ? WHERE id = ?",
                        (lowest_price, store, link, title, scan_json, now_str, product_id)
                    )
                else:
                    conn.execute(
                        "UPDATE monitored_products SET current_lowest_price = ?, lowest_store = ?, lowest_link = ?, last_title = ?, last_checked_at = ? WHERE id = ?",
                        (lowest_price, store, link, title, now_str, product_id)
                    )
            except sqlite3.OperationalError:
                conn.execute(
                    "UPDATE monitored_products SET current_lowest_price = ?, lowest_store = ?, lowest_link = ?, last_checked_at = ? WHERE id = ?",
                    (lowest_price, store, link, now_str, product_id)
                )
            _async_sync_products()

    @staticmethod
    def update_product_scan_status(product_id: int, scan_snapshot: Dict[str, Any]):
        """Registra horário e snapshot da varredura mesmo quando nenhuma oferta válida é encontrada."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        scan_json = json.dumps(scan_snapshot, ensure_ascii=False)
        with get_db() as conn:
            try:
                conn.execute(
                    "UPDATE monitored_products SET last_scan_json = ?, last_checked_at = ? WHERE id = ?",
                    (scan_json, now_str, product_id)
                )
            except sqlite3.OperationalError:
                conn.execute(
                    "UPDATE monitored_products SET last_checked_at = ? WHERE id = ?",
                    (now_str, product_id)
                )

    @staticmethod
    def edit_monitored_product(product_id: int, new_keyword: str, new_target_price: float, update_history: bool = True) -> bool:
        """Edita a palavra-chave e/ou preço-alvo de um produto monitorado."""
        with get_db() as conn:
            old_prod = conn.execute("SELECT keyword FROM monitored_products WHERE id = ?", (product_id,)).fetchone()
            if not old_prod:
                return False
            old_kw = old_prod["keyword"]
            clean_new = new_keyword.strip()

            # Se o termo mudou
            if old_kw.lower() != clean_new.lower():
                try:
                    conn.execute(
                        "UPDATE monitored_products SET keyword = ?, target_price = ?, current_lowest_price = NULL, lowest_store = NULL, lowest_link = NULL, last_title = '', last_scan_json = '', last_checked_at = NULL WHERE id = ?",
                        (clean_new, float(new_target_price), product_id)
                    )
                except sqlite3.OperationalError:
                    conn.execute(
                        "UPDATE monitored_products SET keyword = ?, target_price = ?, current_lowest_price = NULL, lowest_store = NULL, lowest_link = NULL, last_checked_at = NULL WHERE id = ?",
                        (clean_new, float(new_target_price), product_id)
                    )
                if update_history:
                    conn.execute(
                        "UPDATE price_history SET keyword = ? WHERE product_id = ? OR keyword = ?",
                        (clean_new, product_id, old_kw)
                    )
            else:
                conn.execute(
                    "UPDATE monitored_products SET target_price = ? WHERE id = ?",
                    (float(new_target_price), product_id)
                )
            _async_sync_products()
            return True

    @staticmethod
    def rename_history_keyword(old_keyword: str, new_keyword: str) -> int:
        """Renomeia uma busca no histórico de preços e sincroniza produtos monitorados se existirem."""
        with get_db() as conn:
            old_clean = old_keyword.strip()
            new_clean = new_keyword.strip()
            res = conn.execute(
                "UPDATE price_history SET keyword = ? WHERE keyword = ?",
                (new_clean, old_clean)
            )
            # Também atualiza em monitored_products se houver
            conn.execute(
                "UPDATE monitored_products SET keyword = ? WHERE keyword = ?",
                (new_clean, old_clean)
            )
            return res.rowcount

    @staticmethod
    def delete_history_by_keyword(keyword: str) -> int:
        """Exclui todos os registros históricos de uma palavra-chave."""
        with get_db() as conn:
            res = conn.execute("DELETE FROM price_history WHERE keyword = ?", (keyword.strip(),))
            return res.rowcount

    @staticmethod
    def delete_history_entry(history_id: int) -> bool:
        """Exclui um registro específico do histórico."""
        with get_db() as conn:
            res = conn.execute("DELETE FROM price_history WHERE id = ?", (history_id,))
            return res.rowcount > 0

    @staticmethod
    def get_recent_search_keywords(limit: int = 8) -> List[str]:
        """Retorna termos de busca recentes para preenchimento rápido."""
        with get_db() as conn:
            rows = conn.execute("""
                SELECT DISTINCT keyword FROM (
                    SELECT keyword, recorded_at FROM price_history
                    UNION
                    SELECT keyword, created_at as recorded_at FROM monitored_products
                ) ORDER BY recorded_at DESC LIMIT ?
            """, (limit,)).fetchall()
            return [r["keyword"] for r in rows if r["keyword"]]

    # --- Histórico de Preços ---
    @staticmethod
    def record_price(product_id: Optional[int], keyword: str, price: float, store: str, title: str, link: str, coupon_code: str = ""):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO price_history (product_id, keyword, price, store, title, link, coupon_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (product_id, keyword.strip(), float(price), store, title, link, coupon_code)
            )
            _async_append_price(product_id, keyword, price, store, title, link, coupon_code)

    @staticmethod
    def get_price_history(keyword: Optional[str] = None, limit: int = 300) -> List[Dict[str, Any]]:
        with get_db() as conn:
            if keyword:
                rows = conn.execute(
                    "SELECT * FROM price_history WHERE keyword = ? ORDER BY recorded_at ASC LIMIT ?",
                    (keyword.strip(), limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM price_history ORDER BY recorded_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def get_historical_min_price(keyword: str) -> Optional[float]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT MIN(price) as min_price FROM price_history WHERE keyword = ? AND price > 0",
                (keyword.strip(),)
            ).fetchone()
            return row["min_price"] if row and row["min_price"] is not None else None

    @staticmethod
    def get_product_stats(keyword: str) -> Dict[str, Any]:
        """Calcula estatísticas de preço para um produto: mínimo, máximo, médio e última variação."""
        with get_db() as conn:
            clean_kw = keyword.strip()
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total_records,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    AVG(price) as avg_price
                FROM price_history
                WHERE keyword = ? AND price > 0
            """, (clean_kw,)).fetchone()

            last_rows = conn.execute("""
                SELECT price FROM price_history
                WHERE keyword = ? AND price > 0
                ORDER BY recorded_at DESC LIMIT 2
            """, (clean_kw,)).fetchall()

            diff_percent = 0.0
            if len(last_rows) >= 2:
                current_p = last_rows[0]["price"]
                prev_p = last_rows[1]["price"]
                if prev_p > 0:
                    diff_percent = round(((current_p - prev_p) / prev_p) * 100, 2)

            return {
                "total_records": row["total_records"] if row else 0,
                "min_price": row["min_price"] if row and row["min_price"] else 0.0,
                "max_price": row["max_price"] if row and row["max_price"] else 0.0,
                "avg_price": round(row["avg_price"], 2) if row and row["avg_price"] else 0.0,
                "diff_percent": diff_percent
            }

    # --- Alertas ---
    @staticmethod
    def log_alert(product_id: Optional[int], phone: str, message: str, status: str):
        with get_db() as conn:
            conn.execute(
                "INSERT INTO alert_logs (product_id, phone, message, status) VALUES (?, ?, ?, ?)",
                (product_id, phone, message, status)
            )

    @staticmethod
    def get_alert_logs(limit: int = 50) -> List[Dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_logs ORDER BY sent_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def get_product_alerts(product_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Retorna os alertas recentes disparados para um produto monitorado específico."""
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_logs WHERE product_id = ? ORDER BY sent_at DESC LIMIT ?",
                (product_id, limit)
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def get_last_successful_alert(product_id: int) -> Optional[Dict[str, Any]]:
        """Retorna o último alerta enviado com sucesso para um produto monitorado."""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM alert_logs WHERE product_id = ? AND status = 'SENT' ORDER BY sent_at DESC LIMIT 1",
                (product_id,)
            ).fetchone()
            return dict(row) if row else None
