import requests
import random
from typing import List
from src.scrapers.base import ProductOffer, USER_AGENTS

class KabumScraper:
    API_URL = "https://servicespub.prod.api.aws.grupokabum.com.br/catalog/v2/products"

    @classmethod
    def search(cls, query: str, limit: int = 15) -> List[ProductOffer]:
        """
        Busca produtos no catálogo oficial da KaBuM! via API REST pública.
        Retorna preços à vista (Pix/desconto), parcelamento, imagens em alta resolução e links diretos.
        """
        offers: List[ProductOffer] = []
        if not query:
            return offers

        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
            "Accept-Language": "pt-BR,pt;q=0.9",
        }
        params = {
            "query": query.strip(),
            "page_number": 1,
            "page_size": min(limit, 20),
        }

        try:
            resp = requests.get(cls.API_URL, params=params, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for item in data:
                    attrs = item.get("attributes", {})
                    prod_id = item.get("id")
                    title = attrs.get("title", "").strip()

                    regular_price = float(attrs.get("price", 0.0) or 0.0)
                    discount_price = float(attrs.get("price_with_discount", 0.0) or 0.0)

                    # Preço efetivo principal (prioriza o preço com desconto à vista)
                    final_price = discount_price if discount_price > 0 else regular_price
                    if final_price <= 0 or not title:
                        continue

                    # URL do Produto
                    friendly = attrs.get("url_friendly", "")
                    if friendly and prod_id:
                        link = f"https://www.kabum.com.br/produto/{prod_id}/{friendly}"
                    elif prod_id:
                        link = f"https://www.kabum.com.br/produto/{prod_id}"
                    else:
                        link = "https://www.kabum.com.br"

                    # Imagem do Produto
                    photos = attrs.get("photos", {})
                    img_url = None
                    if isinstance(photos, dict):
                        img_url = photos.get("g") or photos.get("m") or photos.get("t")
                    if not img_url:
                        img_url = attrs.get("image")

                    # Avaliação
                    rating = attrs.get("rating")
                    try:
                        rating_val = float(rating) if rating is not None else None
                    except (ValueError, TypeError):
                        rating_val = None

                    # Parcelamento
                    installments = None
                    if regular_price > final_price:
                        installments = f"Preço a prazo: R$ {regular_price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                    offers.append(
                        ProductOffer(
                            title=title,
                            price=round(final_price, 2),
                            cash_price=round(discount_price, 2) if discount_price > 0 else None,
                            original_price=round(regular_price, 2) if regular_price > final_price else None,
                            installments=installments,
                            store="KaBuM!",
                            link=link,
                            image_url=img_url,
                            rating=rating_val,
                            source="kabum"
                        )
                    )
        except Exception:
            pass

        return offers
