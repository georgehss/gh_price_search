from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional
from src.scrapers.base import ProductOffer
from src.scrapers.google_shopping import (
    BuscapeScraper,
    ZoomScraper,
    BondfaroScraper,
    GoogleShoppingScraper,
)
from src.scrapers.kabum import KabumScraper
from src.scrapers.carrefour import CarrefourScraper
from src.scrapers.mercado_livre import MercadoLivreScraper
from src.scrapers.coupons import CouponScraper
from src.scrapers.relevance import ProductRelevanceFilter


class UnifiedSearchEngine:
    @staticmethod
    def _build_focused_query(query: str) -> Optional[str]:
        """
        Extrai uma query focada (marca + modelo) quando a busca original tem muitas palavras
        genéricas, melhorando a precisão em APIs de busca exata (ex: 'Caixa De Som Bluetooth Ecopower Ep-s314' -> 'Ecopower Ep-s314').
        """
        tokens = ProductRelevanceFilter.extract_tokens(query)
        if len(tokens) < 4:
            return None
        brand = ProductRelevanceFilter.infer_brand_token(tokens)
        codes = ProductRelevanceFilter.extract_model_codes(ProductRelevanceFilter.normalize_text(query))
        if not codes:
            return None

        # Preserva tokens com código do modelo e a marca
        raw_words = query.strip().split()
        focused_parts = []
        for w in raw_words:
            w_norm = ProductRelevanceFilter.normalize_text(w)
            if brand and brand in w_norm and w not in focused_parts:
                focused_parts.append(w)
            elif any(c in w_norm.replace(" ", "") for c in codes) and w not in focused_parts:
                focused_parts.append(w)

        focused = " ".join(focused_parts).strip()
        if focused and focused.lower() != query.strip().lower():
            return focused
        return None

    @classmethod
    def _run_scrapers(cls, query: str) -> tuple[List[ProductOffer], Dict[str, str]]:
        all_offers: List[ProductOffer] = []
        source_status: Dict[str, str] = {}

        sources = [
            ("KaBuM!", KabumScraper, 10),
            ("Buscapé", BuscapeScraper, 15),
            ("Zoom", ZoomScraper, 10),
            ("Bondfaro", BondfaroScraper, 10),
            ("Carrefour", CarrefourScraper, 10),
            ("Mercado Livre", MercadoLivreScraper, 10),
            ("Google Shopping", GoogleShoppingScraper, 10),
        ]

        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = {
                name: (scraper_cls, executor.submit(scraper_cls.search, query, limit))
                for name, scraper_cls, limit in sources
            }

            for name, (scraper_cls, fut) in futures.items():
                try:
                    res = fut.result(timeout=12)
                    all_offers.extend(res)
                    status_flag = getattr(scraper_cls, "last_status", "ok")
                    if res:
                        source_status[name] = f"{len(res)} coletada(s)"
                    elif status_flag.startswith("blocked"):
                        source_status[name] = "bloqueado (requer API/login)"
                    elif status_flag != "ok":
                        source_status[name] = f"indisponível ({status_flag})"
                    else:
                        source_status[name] = "0 encontradas"
                except Exception:
                    source_status[name] = "tempo esgotado"

        return all_offers, source_status

    @classmethod
    def search_all(cls, query: str) -> Dict[str, Any]:
        """
        Executa busca paralela e unificada em todas as fontes disponíveis:
        - KaBuM!, Carrefour, Buscapé, Zoom, Bondfaro, Mercado Livre e Google Shopping
        - Cupons ativos e verificados (Cuponomia por loja e Promobit)
        """
        clean_query = query.strip()
        if not clean_query:
            return {
                "query": query,
                "total_found": 0,
                "best_deal": None,
                "top_offers": [],
                "coupons": [],
                "source_status": {},
            }

        all_offers, source_status = cls._run_scrapers(clean_query)

        # Filtragem rigorosa de relevância anti-divergência e extração de alternativas da marca
        classification = ProductRelevanceFilter.filter_and_classify_offers(clean_query, all_offers)
        raw_valid = classification["valid_offers"]

        # Se nenhuma oferta exata foi encontrada e a query for longa, tenta query focada (marca + modelo)
        if not raw_valid:
            focused_q = cls._build_focused_query(clean_query)
            if focused_q:
                extra_offers, extra_status = cls._run_scrapers(focused_q)
                if extra_offers:
                    all_offers.extend(extra_offers)
                    classification = ProductRelevanceFilter.filter_and_classify_offers(clean_query, all_offers)
                    raw_valid = classification["valid_offers"]
                for k, v in extra_status.items():
                    if "coletada" in v and "0 encontradas" in source_status.get(k, ""):
                        source_status[k] = v

        brand_alternatives = classification["brand_alternatives"]

        # Deduplicação inteligente de ofertas aprovadas
        deduped: List[ProductOffer] = []
        seen = set()
        for o in raw_valid:
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
            "coupons": coupons_list,
            "source_status": source_status,
        }
