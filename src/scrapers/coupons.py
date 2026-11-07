import requests
import random
import json
import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from src.scrapers.base import CouponOffer, USER_AGENTS

# Mapeamento de nomes de lojas populares para seus slugs no Cuponomia
STORE_SLUG_MAP = {
    "amazon": "amazon",
    "kabum": "kabum",
    "ka bum": "kabum",
    "magazine luiza": "magazine-luiza",
    "magalu": "magazine-luiza",
    "mercado livre": "mercado-livre",
    "shopee": "shopee",
    "casas bahia": "casas-bahia",
    "aliexpress": "aliexpress",
    "americanas": "americanas",
    "samsung": "samsung",
    "fast shop": "fast-shop",
    "submarino": "submarino",
    "ponto frio": "ponto-frio",
    "ponto": "ponto-frio",
    "nike": "nike",
    "adidas": "adidas",
    "dell": "dell",
    "netshoes": "netshoes",
}

class CouponScraper:
    CUPONOMIA_BASE = "https://www.cuponomia.com.br/desconto"
    PROMOBIT_BASE = "https://www.promobit.com.br/promocoes"

    @classmethod
    def resolve_store_slug(cls, name_or_query: str) -> Optional[str]:
        """Resolve o nome ou query para o slug de loja correspondente."""
        clean = name_or_query.lower().strip()
        clean = re.sub(r"[^\w\s]", "", clean)
        for key, slug in STORE_SLUG_MAP.items():
            if key in clean or slug in clean:
                return slug
        return None

    @classmethod
    def fetch_store_coupons_cuponomia(cls, store_slug: str, limit: int = 5) -> List[CouponOffer]:
        """
        Coleta cupons ativos e verificados de uma loja no Cuponomia.
        """
        coupons: List[CouponOffer] = []
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
        url = f"{cls.CUPONOMIA_BASE}/{store_slug}"

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".coupon-info, .js-coupon-info, li[data-coupon-id]")
                for it in items[:limit]:
                    title_elem = it.select_one(".coupon-info-title, .coupon-title, h3, a")
                    desc_elem = it.select_one(".coupon-info-complement, .item-desc, p")

                    title = title_elem.get_text(strip=True) if title_elem else "Desconto no site"
                    desc = desc_elem.get_text(strip=True) if desc_elem else ""

                    # Identifica se há código ou se é link de ativação
                    code_elem = it.select_one(".coupon-code, [data-code], .js-coupon-code")
                    code = code_elem.get_text(strip=True) if code_elem else "ATIVAR NO SITE"

                    store_display = store_slug.replace("-", " ").title()

                    coupons.append(
                        CouponOffer(
                            code=code,
                            store=store_display,
                            description=f"{title} - {desc}".strip(" -"),
                            link=url
                        )
                    )
        except Exception:
            pass

        return coupons

    @classmethod
    def fetch_promobit_featured_coupons(cls, limit: int = 5) -> List[CouponOffer]:
        """
        Coleta cupons verificados em destaque na comunidade Promobit via hidratação Next.js.
        """
        coupons: List[CouponOffer] = []
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }

        try:
            resp = requests.get(cls.PROMOBIT_BASE, headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                next_script = soup.select_one("#__NEXT_DATA__")
                if next_script and next_script.string:
                    props = json.loads(next_script.string).get("props", {}).get("pageProps", {})
                    raw_coupons = props.get("serverCoupons", [])
                    for c in raw_coupons[:limit]:
                        code = c.get("couponCode") or "VER OFERTA"
                        store = c.get("storeName") or "Promobit"
                        discount = c.get("couponDiscountShort") or ""
                        title = c.get("couponTitle") or "Cupom de Desconto"

                        desc = f"{discount}: {title}" if discount else title

                        coupons.append(
                            CouponOffer(
                                code=code,
                                store=store,
                                description=desc,
                                link="https://www.promobit.com.br/promocoes"
                            )
                        )
        except Exception:
            pass

        return coupons

    @classmethod
    def search_all_relevant_coupons(cls, query: str, stores_found: Optional[List[str]] = None, limit: int = 6) -> List[CouponOffer]:
        """
        Busca inteligente:
        1. Identifica se a busca do produto menciona alguma loja ou se as ofertas encontradas são de lojas conhecidas.
        2. Coleta cupons ativos dessas lojas no Cuponomia.
        3. Adiciona cupons em destaque gerais da comunidade Promobit.
        """
        all_coupons: List[CouponOffer] = []
        seen_codes = set()

        # 1. Checar lojas a partir do query ou das ofertas
        target_slugs = set()
        query_slug = cls.resolve_store_slug(query)
        if query_slug:
            target_slugs.add(query_slug)

        if stores_found:
            for s in stores_found:
                slug = cls.resolve_store_slug(s)
                if slug:
                    target_slugs.add(slug)

        # Se nenhuma loja foi detectada, carrega as lojas mais comuns de eletrônicos/e-commerce
        if not target_slugs:
            target_slugs.update(["amazon", "kabum", "mercado-livre", "magazine-luiza"])

        # 2. Buscar cupons de cada loja alvo
        for slug in list(target_slugs)[:3]:
            store_coupons = cls.fetch_store_coupons_cuponomia(slug, limit=3)
            for c in store_coupons:
                key = (c.code, c.store, c.description[:30])
                if key not in seen_codes:
                    seen_codes.add(key)
                    all_coupons.append(c)

        # 3. Adicionar cupons da comunidade Promobit
        promobit_coupons = cls.fetch_promobit_featured_coupons(limit=3)
        for c in promobit_coupons:
            key = (c.code, c.store, c.description[:30])
            if key not in seen_codes:
                seen_codes.add(key)
                all_coupons.append(c)

        return all_coupons[:limit]

    # Métodos de compatibilidade retroativa
    @classmethod
    def search_pelando(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        return []

    @classmethod
    def search_promobit(cls, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        coupons = cls.fetch_promobit_featured_coupons(limit=limit)
        return [c.to_dict() for c in coupons]

    @classmethod
    def search_cuponomia(cls, store_or_product: str, limit: int = 5) -> List[CouponOffer]:
        slug = cls.resolve_store_slug(store_or_product) or "amazon"
        return cls.fetch_store_coupons_cuponomia(slug, limit=limit)
