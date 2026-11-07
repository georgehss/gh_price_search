import json
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger("GHPriceSearch.GSheets")

class GoogleSheetsSync:
    """
    Gerencia a sincronização bidirecional entre o banco local (SQLite)
    e uma planilha no Google Drive via Google Sheets API (gspread).
    """

    _client = None
    _spreadsheet = None

    @classmethod
    def get_client(cls):
        """Inicializa e retorna o cliente autenticado do gspread."""
        if cls._client is not None:
            return cls._client

        from src.config import Config
        credentials_dict = Config.get_gsheets_credentials()
        if not credentials_dict:
            return None

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"
            ]
            creds = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
            cls._client = gspread.authorize(creds)
            return cls._client
        except Exception as e:
            logger.warning(f"Erro ao autenticar com Google Sheets: {e}")
            return None

    @classmethod
    def get_spreadsheet(cls):
        """Retorna ou abre a planilha no Google Drive."""
        if cls._spreadsheet is not None:
            return cls._spreadsheet

        client = cls.get_client()
        if not client:
            return None

        from src.config import Config
        sheet_target = Config.GSHEETS_URL or Config.GSHEETS_NAME or "GH Price Search Data"

        try:
            if sheet_target.startswith("https://"):
                cls._spreadsheet = client.open_by_url(sheet_target)
            else:
                try:
                    cls._spreadsheet = client.open(sheet_target)
                except Exception:
                    # Se não existir, tenta criar uma nova no Drive
                    cls._spreadsheet = client.create(sheet_target)
            cls._ensure_worksheets()
            return cls._spreadsheet
        except Exception as e:
            logger.warning(f"Erro ao abrir planilha do Google Sheets '{sheet_target}': {e}")
            return None

    @classmethod
    def _ensure_worksheets(cls):
        """Garante que as abas com os cabeçalhos corretos existam na planilha."""
        if not cls._spreadsheet:
            return
        
        expected_sheets = {
            "monitored_products": [
                "id", "keyword", "target_price", "is_active", 
                "current_lowest_price", "lowest_store", "lowest_link", 
                "last_title", "last_checked_at", "created_at"
            ],
            "price_history": [
                "id", "product_id", "keyword", "price", "store", 
                "title", "link", "coupon_code", "recorded_at"
            ],
            "alert_logs": [
                "id", "product_id", "phone", "message", "status", "sent_at"
            ]
        }

        existing_titles = [ws.title for ws in cls._spreadsheet.worksheets()]
        for title, headers in expected_sheets.items():
            if title not in existing_titles:
                try:
                    ws = cls._spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers) + 2)
                    ws.append_row(headers)
                except Exception as e:
                    logger.warning(f"Erro ao criar aba {title}: {e}")

    @classmethod
    def pull_to_sqlite(cls):
        """
        Restaura produtos do Google Sheets para o SQLite local caso o banco local esteja vazio
        (essencial quando o Streamlit Cloud reinicia o container).
        """
        client = cls.get_client()
        if not client:
            return

        try:
            sh = cls.get_spreadsheet()
            if not sh:
                return

            ws = sh.worksheet("monitored_products")
            records = ws.get_all_records()
            if not records:
                return

            from src.database.db import get_db
            with get_db() as conn:
                count_row = conn.execute("SELECT COUNT(*) as c FROM monitored_products").fetchone()
                if count_row and count_row["c"] == 0:
                    for r in records:
                        kw = str(r.get("keyword", "")).strip()
                        if not kw:
                            continue
                        conn.execute("""
                            INSERT OR REPLACE INTO monitored_products 
                            (id, keyword, target_price, is_active, current_lowest_price, lowest_store, lowest_link, last_title, last_checked_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            r.get("id") or None,
                            kw,
                            float(r.get("target_price") or 0.0),
                            int(r.get("is_active", 1)),
                            float(r.get("current_lowest_price") or 0.0) if r.get("current_lowest_price") else None,
                            r.get("lowest_store") or None,
                            r.get("lowest_link") or None,
                            r.get("last_title") or None,
                            r.get("last_checked_at") or None
                        ))
                    logger.info(f"Sincronizados {len(records)} produtos do Google Sheets para o SQLite.")
        except Exception as e:
            logger.warning(f"Falha ao puxar dados do Google Sheets: {e}")

    @classmethod
    def sync_monitored_products(cls):
        """Exporta todos os produtos monitorados do SQLite para a planilha Google Sheets."""
        try:
            sh = cls.get_spreadsheet()
            if not sh:
                return
            ws = sh.worksheet("monitored_products")
            
            from src.database.models import DatabaseManager
            products = DatabaseManager.get_monitored_products(active_only=False)
            
            headers = [
                "id", "keyword", "target_price", "is_active", 
                "current_lowest_price", "lowest_store", "lowest_link", 
                "last_title", "last_checked_at", "created_at"
            ]
            rows = [headers]
            for p in products:
                rows.append([
                    p.get("id", ""),
                    p.get("keyword", ""),
                    p.get("target_price", 0.0),
                    p.get("is_active", 1),
                    p.get("current_lowest_price", ""),
                    p.get("lowest_store", ""),
                    p.get("lowest_link", ""),
                    p.get("last_title", ""),
                    p.get("last_checked_at", ""),
                    p.get("created_at", "")
                ])
            ws.clear()
            ws.update(rows)
        except Exception as e:
            logger.warning(f"Erro ao salvar produtos no Google Sheets: {e}")

    @classmethod
    def append_price_record(cls, product_id: Optional[int], keyword: str, price: float, store: str, title: str, link: str, coupon_code: str = ""):
        """Adiciona uma linha no histórico de preços na planilha Google Sheets."""
        try:
            sh = cls.get_spreadsheet()
            if not sh:
                return
            from datetime import datetime
            ws = sh.worksheet("price_history")
            ws.append_row([
                "", product_id or "", keyword, price, store, title, link, coupon_code, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ])
        except Exception as e:
            logger.warning(f"Erro ao registrar histórico no Google Sheets: {e}")
