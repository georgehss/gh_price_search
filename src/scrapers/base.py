import re
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

def parse_br_price(price_text: Any) -> float:
    """
    Converte strings de preço em formato brasileiro (ex: 'R$ 1.499,90', '1.499,00', '1499.00') em float.
    """
    if price_text is None:
        return 0.0
    if isinstance(price_text, (int, float)):
        return round(float(price_text), 2)

    raw = str(price_text).strip()
    if not raw:
        return 0.0

    # Busca padrão de preço monetário com possíveis separadores
    match = re.search(r"(\d+(?:[\.,]\d+)*)", raw)
    if not match:
        return 0.0

    clean = match.group(1).strip()
    if not clean:
        return 0.0

    # Se houver vírgula e ponto, ex: 1.499,90
    if "," in clean and "." in clean:
        clean = clean.replace(".", "").replace(",", ".")
    elif "," in clean:
        # Se só tem vírgula, ex: 1499,90 ou 1,499
        parts = clean.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # Caso raro de separador de milhar com vírgula
            clean = clean.replace(",", "")
        else:
            clean = clean.replace(",", ".")
    elif "." in clean:
        # Se só tem ponto, verificar se é milhar (1.499) ou decimal (1499.90)
        parts = clean.split(".")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
            # Provável milhar: 1.499 -> 1499
            clean = clean.replace(".", "")

    try:
        val = float(clean)
        return round(val, 2)
    except ValueError:
        return 0.0

@dataclass
class ProductOffer:
    title: str
    price: float
    store: str
    link: str
    cash_price: Optional[float] = None
    original_price: Optional[float] = None
    installments: Optional[str] = None
    image_url: Optional[str] = None
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    source: str = "web"
    coupon_code: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class CouponOffer:
    code: str
    store: str
    description: str
    discount_value: Optional[str] = None
    link: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
