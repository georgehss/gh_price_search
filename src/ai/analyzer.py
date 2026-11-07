import json
import re
from typing import Dict, Any, List, Optional
from src.config import Config

class DealAIAnalyzer:
    @classmethod
    def clean_whatsapp_text(cls, text: str) -> str:
        """
        Converte markdown padrão (HTML/GitHub) para a sintaxe nativa aceita pelo WhatsApp:
        - Transforma **texto** em *texto*
        - Remove marcadores de cabeçalho como '### ' ou '## '
        - Converte links no formato [Texto](url) para 'Texto: url'
        """
        if not text:
            return ""

        # Remove cabeçalhos markdown tipo ### ou ##
        cleaned = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        # Converte [Titulo](link) -> Titulo (link)
        cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1: \2", cleaned)
        # Converte **negrito duplo** em *negrito simples*
        cleaned = re.sub(r"\*\*([^\*]+)\*\*", r"*\1*", cleaned)
        # Remove blocos de código tipo ```texto```
        cleaned = re.sub(r"```[a-zA-Z]*\n?", "", cleaned)
        return cleaned.strip()

    @classmethod
    def analyze_deals(
        cls,
        query: str,
        best_deal: Optional[Dict[str, Any]],
        top_offers: List[Dict[str, Any]],
        coupons: List[Dict[str, Any]],
        historical_min: Optional[float] = None,
        brand_alternatives: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Usa o Google Gemini para analisar os resultados de preço, reputação, cupons e custo-benefício.
        Possui suporte completo a produtos não encontrados e fallback algorítmico robusto.
        """
        brand_alternatives = brand_alternatives or []

        # Se não houver chave de API configurada, utiliza análise algorítmica
        if not Config.GEMINI_API_KEY:
            if not best_deal or not top_offers:
                return cls._not_found_analysis(query, brand_alternatives)
            return cls._fallback_analysis(query, best_deal, top_offers, coupons, historical_min)

        try:
            from google import genai
            client = genai.Client(api_key=Config.GEMINI_API_KEY)

            # Caso 1: Produto não encontrado nas lojas consultadas
            if not best_deal or not top_offers:
                alts_summary = [
                    {"titulo": a.get("title"), "preco": a.get("price"), "loja": a.get("store")}
                    for a in brand_alternatives[:4]
                ]
                prompt = f"""Você é o analista de compras do GH Price Search Bot.
O usuário pesquisou pelo produto '{query}', mas nenhuma loja integrada possui esse modelo exato em estoque no momento.
Resultados divergentes retornados por buscadores (como mouse pads, filtros ou peças automotivas) foram descartados pelo filtro de segurança.
Modelos alternativos da mesma marca encontrados:
{json.dumps(alts_summary, indent=2, ensure_ascii=False)}

Instruções:
1. Confirme que o modelo exato '{query}' não foi encontrado em estoque nas grandes lojas.
2. Alerte expressamente para o usuário não comprar produtos divergentes sugeridos por buscas genéricas (como mouse pads ou acessórios).
3. Se houver modelos alternativos da marca acima, mencione-os brevemente como opções.
4. Responda em no máximo 3 a 4 linhas curtas em tom executivo.
5. Formate exclusivamente para WhatsApp usando apenas *negrito com um asterisco* (NÃO USE asteriscos duplos nem ###)."""

            # Caso 2: Ofertas válidas encontradas
            else:
                offers_summary = []
                for o in top_offers[:8]:
                    offers_summary.append({
                        "loja": o.get("store"),
                        "titulo": o.get("title"),
                        "preco": o.get("price"),
                        "a_vista_pix": o.get("cash_price"),
                        "parcelas": o.get("installments"),
                        "link": o.get("link")
                    })

                coupons_summary = [
                    f"{c.get('code')}: {c.get('store')} ({c.get('description')})"
                    for c in coupons[:5] if c.get("code")
                ]

                prompt = f"""Você é o analista de compras inteligente do GH Price Search Bot.
Analise com rigor as ofertas abaixo para a pesquisa '{query}'.

Ofertas encontradas:
{json.dumps(offers_summary, indent=2, ensure_ascii=False)}

Cupons identificados:
{json.dumps(coupons_summary, ensure_ascii=False)}

Menor preço histórico registrado no banco: R$ {historical_min if historical_min else 'Sem registro prévio'}

Instruções obrigatórias:
1. Avalie o MENOR PREÇO e o MELHOR CUSTO-BENEFÍCIO (considere confiabilidade da loja e se o produto corresponde exatamente ao buscado).
2. Verifique se o preço parece suspeito/golpe (ex: acessório com nome de console, ou valor absurdamente abaixo da média).
3. Analise se há desconto real no Pix ou cupom que compense.
4. Responda em no máximo 4 a 5 linhas curtas com tom executivo e direto.
5. Formate exclusivamente para WhatsApp usando apenas *negrito com um asterisco* (NÃO USE asteriscos duplos ** nem cabeçalhos markdown ###)."""

            # Cadeia de modelos: gemini-3.8-flash -> gemini-3.5-flash-lite -> gemini-3.5-flash
            response = None
            models_to_try = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
            last_err = None

            for m in models_to_try:
                try:
                    res = client.models.generate_content(model=m, contents=prompt)
                    if res and res.text:
                        response = res
                        break
                except Exception as e:
                    last_err = e
                    continue

            if response and response.text:
                verdict_text = cls.clean_whatsapp_text(response.text)
                return {
                    "verdict": verdict_text,
                    "source": "gemini"
                }
            else:
                if not best_deal or not top_offers:
                    fallback = cls._not_found_analysis(query, brand_alternatives)
                else:
                    fallback = cls._fallback_analysis(query, best_deal, top_offers, coupons, historical_min)
                if last_err:
                    fallback["warning"] = f"Gemini temporariamente indisponível: {str(last_err)}"
                return fallback

        except Exception as e:
            if not best_deal or not top_offers:
                fallback = cls._not_found_analysis(query, brand_alternatives)
            else:
                fallback = cls._fallback_analysis(query, best_deal, top_offers, coupons, historical_min)
            fallback["warning"] = f"Análise via IA em modo heurístico: {str(e)}"
            return fallback

    @classmethod
    def _not_found_analysis(
        cls,
        query: str,
        brand_alternatives: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Análise algorítmica de apoio quando o produto específico não for encontrado."""
        alts = brand_alternatives or []
        lines = []
        lines.append(f"⚠️ *Produto não localizado:* O modelo exato *{query}* não possui ofertas ativas nas lojas consultadas.")
        lines.append("🛡️ *Alerta de segurança:* Os comparadores de preço retornaram apenas acessórios ou itens incompatíveis de outras categorias, que foram devidamente descartados pelo filtro de relevância.")
        if alts:
            alt_names = [f"*{a.get('title', '')[:35]}* (R$ {a.get('price', 0):,.2f})".replace(",", "X").replace(".", ",").replace("X", ".") for a in alts[:2]]
            lines.append(f"💡 *Alternativas da marca:* Encontramos outros modelos da fabricante: {', '.join(alt_names)}.")
        else:
            lines.append("💡 *Recomendação:* Consulte a loja oficial do fabricante ou o Mercado Livre para checar a disponibilidade deste modelo.")
        return {
            "verdict": "\n".join(lines),
            "source": "heuristic"
        }

    @classmethod
    def _fallback_analysis(
        cls,
        query: str,
        best_deal: Dict[str, Any],
        top_offers: List[Dict[str, Any]],
        coupons: List[Dict[str, Any]],
        historical_min: Optional[float]
    ) -> Dict[str, Any]:
        """Análise algorítmica de apoio quando Gemini não estiver disponível."""
        min_price = best_deal.get("price", 0.0)
        store = best_deal.get("store", "Loja Online")

        lines = []
        p_str = f"R$ {min_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        lines.append(f"✅ *Melhor oferta identificada:* {p_str} na *{store}*.")

        # Análise histórica
        if historical_min and historical_min > 0:
            hist_str = f"R$ {historical_min:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            if min_price <= historical_min:
                lines.append(f"🔥 *Excelente momento:* Preço no menor patamar histórico registrado ({hist_str})!")
            else:
                lines.append(f"ℹ️ O menor preço histórico registrado para este item foi {hist_str}.")

        # Dica de Cupons / Pagamento
        if coupons:
            sample_c = coupons[0].get("code", "ativo")
            lines.append(f"🎟️ *Dica de economia:* Teste o cupom *{sample_c}* antes de finalizar.")
        else:
            lines.append("💡 *Dica:* Verifique a opção de pagamento via Pix para descontos adicionais de até 10%.")

        return {
            "verdict": "\n".join(lines),
            "source": "heuristic"
        }
