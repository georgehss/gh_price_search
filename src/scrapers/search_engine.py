from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from src.scrapers.base import ProductOffer, CouponOffer
from src.scrapers.google_shopping import BuscapeScraper, ZoomScraper, GoogleShoppingScraper
from src.scrapers.kabum import KabumScraper
from src.scrapers.mercado_livre import MercadoLivreScraper
from src.scrapers.coupons import CouponScraper
from src.scrapers.relevance import ProductRelevanceFilter

class UnifiedSearchEngine:
    @classmethod
    def search_all(cls, query: str) -> Dict[str, Any]:
        """
        Executa busca paralela e unificada em todas as fontes disponíveis:
        - KaBuM! (API de catálogo com preços à vista/Pix e fotos)
        - Buscapé (agregando Amazon, Americanas, Magalu e centenas de lojas com nomes reais)
        - Zoom (comparador adicional)
        - Mercado Livre
        - Google Shopping
        - Cupons ativos e verificados (Cuponomia por loja e Promobit)
        """
        all_offers: List[ProductOffer] = []
        clean_query = query.strip()
        if not clean_query:
            return {
                "query": query,
                "total_found": 0,
                "best_deal": None,
                "top_offers": [],
                "coupons": []
            }

        with ThreadPoolExecutor(max_workers=6) as executor:
            # Tarefas paralelas de produtos
            future_kabum = executor.submit(KabumScraper.search, clean_query, 10)
            future_buscape = executor.submit(BuscapeScraper.search, clean_query, 15)
            future_zoom = executor.submit(ZoomScraper.search, clean_query, 10)
            future_ml = executor.submit(MercadoLivreScraper.search, clean_query, 10)
            future_gshop = executor.submit(GoogleShoppingScraper.search, clean_query, 10)

            # Coletar KaBuM!
            try:
                all_offers.extend(future_kabum.result(timeout=10))
            except Exception:
                pass

            # Coletar Buscapé
            try:
                all_offers.extend(future_buscape.result(timeout=10))
            except Exception:
                pass

            # Coletar Zoom
            try:
                all_offers.extend(future_zoom.result(timeout=10))
            except Exception:
                pass

            # Coletar Mercado Livre
            try:
                all_offers.extend(future_ml.result(timeout=10))
            except Exception:
                pass

            # Coletar Google Shopping
            try:
                all_offers.extend(future_gshop.result(timeout=10))
            except Exception:
                pass

        # Filtragem rigorosa de relevância anti-divergência e extração de alternativas da marca
        classification = ProductRelevanceFilter.filter_and_classify_offers(clean_query, all_offers)
        raw_valid = classification["valid_offers"]
        brand_alternatives = classification["brand_alternatives"]

        # Deduplicação inteligente de ofertas aprovadas
        deduped: List[ProductOffer] = []
        seen = set()
        for o in raw_valid:
            # Chave de unicidade combinando loja e título simplificado
            clean_title = "".join(c for c in o.title.lower() if c.isalnum())[:25]
            key = (round(o.price, 2), o.store.lower(), clean_title)
            if key not in seen:
                seen.add(key)
                deduped.append(o)

        # Identificar lojas encontradas para buscar cupons relevantes
        stores_found = [o.store for o in deduped]
        if not stores_found and brand_alternatives:
            stores_found = [o.store for o in brand_alternatives]
        coupons = CouponScraper.search_all_relevant_coupons(clean_query, stores_found=stores_found, limit=6)

        best_deal = deduped[0].to_dict() if deduped else None
        top_offers = [o.to_dict() for o in deduped[:25]]
        brand_alts_list = [a.to_dict() for a in brand_alternatives]
        coupons_list = [c.to_dict() for c in coupons]

        return {
            "query": query,
            "total_found": len(deduped),
            "best_deal": best_deal,
            "top_offers": top_offers,
            "brand_alternatives": brand_alts_list,
            "rejected_count": classification["rejected_count"],
            "rejections": classification.get("rejections", []),
            "coupons": coupons_list
        }
