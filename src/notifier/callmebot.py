import urllib.parse
import requests
import re
from typing import Optional, Dict, Any, List
from src.config import Config
from src.database.models import DatabaseManager

class CallMeBotNotifier:
    BASE_URL = "https://api.callmebot.com/whatsapp.php"

    @staticmethod
    def clean_phone(phone: str) -> str:
        """Limpa o número de telefone, mantendo formato internacional como +5511999999999."""
        if not phone:
            return ""
        # Remove caracteres que não sejam números ou '+'
        cleaned = re.sub(r"[^\d+]", "", phone.strip())
        if not cleaned.startswith("+"):
            # Se não tiver o +, adiciona se começar com 55 ou código de país
            if len(cleaned) in [10, 11]:  # DDD + Número Brasil sem 55
                cleaned = "+55" + cleaned
            else:
                cleaned = "+" + cleaned
        return cleaned

    @classmethod
    def _send_request(cls, target_phone: str, message: str, target_key: str, product_id: Optional[int] = None) -> Dict[str, Any]:
        # Formata URL garantindo %20 para espaços
        encoded_phone = urllib.parse.quote(target_phone)
        encoded_text = urllib.parse.quote(message)
        encoded_key = urllib.parse.quote(target_key)

        url = f"{cls.BASE_URL}?phone={encoded_phone}&text={encoded_text}&apikey={encoded_key}"

        try:
            response = requests.get(url, timeout=20)
            resp_text = response.text.lower()
            if response.status_code == 200 and ("queued" in resp_text or "success" in resp_text or "ok" in resp_text):
                DatabaseManager.log_alert(product_id, target_phone, message, "SENT")
                return {"success": True, "response": response.text, "phone_used": target_phone}
            else:
                error_msg = f"Resposta CallMeBot ({response.status_code}): {response.text.strip()}"
                DatabaseManager.log_alert(product_id, target_phone, message, f"FAILED: {error_msg}")
                return {"success": False, "error": error_msg}
        except requests.exceptions.RequestException as e:
            error_msg = f"Falha de conexão com CallMeBot: {str(e)}"
            DatabaseManager.log_alert(product_id, target_phone, message, f"FAILED: {error_msg}")
            return {"success": False, "error": error_msg}

    @classmethod
    def send_message(cls, message: str, phone: Optional[str] = None, apikey: Optional[str] = None, product_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Envia uma mensagem de WhatsApp via CallMeBot com suporte a retry inteligente do 9º dígito.
        """
        target_phone = cls.clean_phone(phone or DatabaseManager.get_setting("user_phone", "") or Config.DEFAULT_PHONE)
        target_key = apikey or Config.CALLMEBOT_API_KEY

        if not target_phone:
            return {"success": False, "error": "Número de telefone não configurado."}
        if not target_key:
            return {"success": False, "error": "Chave de API do CallMeBot não configurada no .env."}

        # Truncar mensagem se for excessivamente longa (limite seguro: 1400 chars)
        if len(message) > 1400:
            message = message[:1350] + "\n\n...[Ver detalhes completos no Painel Web]"

        # 1. Tentativa com o número fornecido
        res = cls._send_request(target_phone, message, target_key, product_id)
        if res.get("success"):
            return res

        # 2. Se falhar com "apikey is invalid" e for número do Brasil (+55),
        # tenta a variação com/sem o 9º dígito (particularidade histórica do WhatsApp no Brasil)
        err_lower = res.get("error", "").lower()
        if "apikey is invalid" in err_lower and target_phone.startswith("+55"):
            digits_only = re.sub(r"\D", "", target_phone)
            alt_phone = None
            if len(digits_only) == 13 and digits_only[4] == "9":
                alt_phone = "+" + digits_only[:4] + digits_only[5:]
            elif len(digits_only) == 12:
                alt_phone = "+" + digits_only[:4] + "9" + digits_only[4:]

            if alt_phone:
                alt_res = cls._send_request(alt_phone, message, target_key, product_id)
                if alt_res.get("success"):
                    DatabaseManager.set_setting("user_phone", alt_phone)
                    Config.save_env_var("DEFAULT_PHONE", alt_phone)
                    alt_res["warning"] = f"Ajustado automaticamente para o formato registrado no CallMeBot: {alt_phone}"
                    return alt_res

        return res

    @classmethod
    def send_deal_report(
        cls,
        keyword: str,
        best_deal: Optional[Dict[str, Any]] = None,
        top_offers: Optional[List[Dict[str, Any]]] = None,
        coupons: Optional[List[Dict[str, Any]]] = None,
        gemini_verdict: Optional[str] = None,
        phone: Optional[str] = None,
        product_id: Optional[int] = None,
        brand_alternatives: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Formata e envia um relatório executivo de melhores ofertas e cupons pronto para leitura no WhatsApp.
        Trata com elegância casos em que o produto não foi encontrado, evitando falsos positivos.
        """
        top_offers = top_offers or []
        coupons = coupons or []
        brand_alternatives = brand_alternatives or []

        lines = []
        lines.append(f"🔍 *GH PRICE SEARCH: {keyword.upper()}*")
        lines.append("────────────────────────")

        if best_deal and best_deal.get("price", 0) > 0:
            price_str = f"R$ {best_deal['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append("🏆 *MENOR PREÇO ENCONTRADO:*")
            lines.append(f"💰 *{price_str}* na *{best_deal.get('store', 'Loja')}*")
            if best_deal.get("installments"):
                lines.append(f"💳 _{best_deal['installments']}_")
            if best_deal.get("title"):
                lines.append(f"📦 _{best_deal['title'][:70]}_")
            if best_deal.get("link"):
                lines.append(f"🔗 {best_deal['link']}")
            lines.append("")

            if coupons:
                lines.append("🎟️ *CUPONS IDENTIFICADOS:*")
                for c in coupons[:3]:
                    code = c.get("code") or "Ver Link"
                    desc = c.get("description") or c.get("store") or "Desconto"
                    lines.append(f"• *{code}*: {desc[:50]}")
                lines.append("")

            if top_offers and len(top_offers) > 1:
                lines.append("🏬 *OUTRAS LOJAS COMPARADAS:*")
                for offer in top_offers[1:4]:
                    p_str = f"R$ {offer['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    lines.append(f"• *{offer.get('store', 'Loja')}*: {p_str}")
                lines.append("")
        else:
            lines.append("⚠️ *PRODUTO NÃO ENCONTRADO EM ESTOQUE*")
            lines.append(f"Não encontramos ofertas confiáveis para *{keyword}* nas lojas integradas (KaBuM!, Buscapé, Zoom).")
            lines.append("")
            lines.append("🛡️ *Filtro Anti-Divergência Ativo:*")
            lines.append("Itens divergentes (como mouse pads, filtros ou acessórios) foram descartados automaticamente para proteger sua compra.")
            lines.append("")

            if brand_alternatives:
                lines.append("📦 *OUTROS MODELOS DA MESMA MARCA ENCONTRADOS:*")
                for alt in brand_alternatives[:3]:
                    p_str = f"R$ {alt['price']:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    lines.append(f"• *{alt.get('title', '')[:50]}*")
                    lines.append(f"  💰 {p_str} na *{alt.get('store', 'Loja')}*")
                    if alt.get("link"):
                        lines.append(f"  🔗 {alt['link']}")
                lines.append("")

        if gemini_verdict:
            lines.append("🧠 *VEREDITO DA IA:*")
            lines.append(f"{gemini_verdict.strip()}")
            lines.append("")

        lines.append("────────────────────────")
        lines.append("🤖 _GH Price Search Bot_")

        full_message = "\n".join(lines)
        return cls.send_message(full_message, phone=phone, product_id=product_id)

    @classmethod
    def send_price_drop_alert(
        cls,
        keyword: str,
        current_price: float,
        target_price: float,
        previous_min: Optional[float],
        store: str,
        link: str,
        phone: Optional[str] = None,
        product_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Envia alerta imediato de queda de preço para um produto monitorado.
        """
        curr_str = f"R$ {current_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        target_str = f"R$ {target_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if target_price > 0 else "N/A"

        lines = [
            "🚨 *ALERTA DE QUEDA DE PREÇO!*",
            f"🎯 Produto: *{keyword}*",
            f"💰 Preço Atual: *{curr_str}*",
            f"🏪 Loja: *{store}*",
        ]

        if target_price > 0 and current_price <= target_price:
            lines.append(f"✅ *Atingiu seu preço-alvo de {target_str}!*")

        if previous_min and current_price < previous_min:
            diff = previous_min - current_price
            diff_str = f"R$ {diff:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"📉 *Menor preço histórico registrado! (Queda de {diff_str})*")

        if link:
            lines.append(f"🔗 Link da Oferta:\n{link}")

        lines.append("\n🤖 _GH Price Search Bot_")

        return cls.send_message("\n".join(lines), phone=phone, product_id=product_id)
