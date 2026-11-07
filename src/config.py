import os
import json
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# Carrega o .env se existir
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

def _get_setting(key: str, default: str = "") -> str:
    """Obtém configuração do ambiente ou dos secrets do Streamlit."""
    val = os.getenv(key)
    if val:
        return val.strip()
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    return default

class Config:
    GEMINI_API_KEY = _get_setting("GEMINI_API_KEY", "")
    CALLMEBOT_API_KEY = _get_setting("CALLMEBOT_API_KEY", "")
    DEFAULT_PHONE = _get_setting("DEFAULT_PHONE", "")
    CHECK_INTERVAL_MINUTES = int(_get_setting("CHECK_INTERVAL_MINUTES", "60") or "60")
    
    # Configurações do Google Sheets (Google Drive)
    GSHEETS_URL = _get_setting("GSHEETS_URL", "")
    GSHEETS_NAME = _get_setting("GSHEETS_NAME", "GH Price Search Data")
    
    DB_PATH = BASE_DIR / "data" / "prices.db"

    @classmethod
    def get_gsheets_credentials(cls) -> dict:
        """
        Retorna o dicionário de credenciais da Service Account do Google.
        Tenta carregar de:
        1. st.secrets["gcp_service_account"]
        2. Variável de ambiente GSHEETS_SERVICE_ACCOUNT_JSON
        3. Arquivo local service_account.json
        """
        # 1. Streamlit Secrets
        try:
            import streamlit as st
            if hasattr(st, "secrets"):
                if "gcp_service_account" in st.secrets:
                    return dict(st.secrets["gcp_service_account"])
                if "connections" in st.secrets and "gsheets" in st.secrets["connections"]:
                    return dict(st.secrets["connections"]["gsheets"])
        except Exception:
            pass

        # 2. Variável de ambiente com JSON em string
        env_json = os.getenv("GSHEETS_SERVICE_ACCOUNT_JSON", "").strip()
        if env_json:
            try:
                return json.loads(env_json)
            except Exception:
                pass

        # 3. Arquivo local service_account.json
        local_file = BASE_DIR / "service_account.json"
        if local_file.exists():
            try:
                with open(local_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        return {}

    @classmethod
    def reload(cls):
        """Recarrega as variáveis do arquivo .env ou secrets."""
        if ENV_PATH.exists():
            load_dotenv(dotenv_path=ENV_PATH, override=True)
        cls.GEMINI_API_KEY = _get_setting("GEMINI_API_KEY", "")
        cls.CALLMEBOT_API_KEY = _get_setting("CALLMEBOT_API_KEY", "")
        cls.DEFAULT_PHONE = _get_setting("DEFAULT_PHONE", "")
        cls.CHECK_INTERVAL_MINUTES = int(_get_setting("CHECK_INTERVAL_MINUTES", "60") or "60")
        cls.GSHEETS_URL = _get_setting("GSHEETS_URL", "")
        cls.GSHEETS_NAME = _get_setting("GSHEETS_NAME", "GH Price Search Data")

    @classmethod
    def save_env_var(cls, key: str, value: str):
        """Salva ou atualiza uma variável no arquivo .env se executando localmente."""
        lines = []
        key_found = False
        if ENV_PATH.exists():
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(f"{key}="):
                        lines.append(f"{key}={value}\n")
                        key_found = True
                    else:
                        lines.append(line)
        if not key_found:
            lines.append(f"{key}={value}\n")
        try:
            with open(ENV_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception:
            pass
        cls.reload()
