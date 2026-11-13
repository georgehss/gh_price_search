import re
import unicodedata
from typing import List, Tuple, Dict, Any, Optional
from src.scrapers.base import ProductOffer

STOPWORDS = {
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "com", "para", "por", "e", "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "pra", "pro", "sem"
}

GENERIC_CATEGORY_WORDS = {
    "caixa", "som", "bluetooth", "speaker", "fone", "ouvido", "headset", "headphone",
    "smartphone", "celular", "notebook", "laptop", "monitor", "tv", "smart",
    "placa", "video", "ssd", "hd", "memoria", "cadeira", "gamer", "controle",
    "console", "tablet", "relogio", "smartwatch", "impressora", "teclado", "mouse",
    "microfone", "camera", "carregador", "portatil", "mini", "pro", "max", "ultra"
}

# Substantivos e termos que caracterizam acessórios/peças quando o usuário NÃO os pesquisou
ACCESSORY_TERMS = [
    # Periféricos, refrigeração e apoios
    "mouse pad", "mousepad", "mouse-pad",
    "suporte", "pedestal", "braco articulado", "tripe", "dock", "docking station",
    "cooler", "ventoinha", "base vertical", "base horizontal", "stand", "organizador",
    "carregador de controle", "dock de carga", "grip", "thumb grip",
    # Proteção e transporte
    "capa", "case", "bolsa", "bag", "estojo", "mochila", "luva", "maleta",
    "pelicula", "adesivo", "skin", "tampa", "faceplate", "cover",
    # Cabos e energia
    "cabo", "carregador", "fonte", "adaptador", "hub", "extensao", "conector",
    "bateria extra", "pilha",
    # Peças e automotivo / limpeza / outros
    "filtro", "vela de ignicao", "pastilha de freio", "amortecedor",
    "shampoo", "condicionador", "sabonete", "desinfetante", "limpador",
    "suplemento", "refrigerante", "cerveja", "porta eletrodo", "fusivel",
    "pulverizador", "carcaca", "peca de reposicao"
]

class ProductRelevanceFilter:
    @staticmethod
    def normalize_text(text: str) -> str:
        """Normaliza texto removendo acentos, caracteres especiais e espaços extras."""
        if not text:
            return ""
        # Remove acentos
        nfkd = unicodedata.normalize("NFKD", text)
        ascii_text = nfkd.encode("ASCII", "ignore").decode("utf-8").lower()
        # Substitui hífens e barras por espaços e preserva caracteres alfanuméricos
        cleaned = re.sub(r"[^\w\s]", " ", ascii_text)
        return " ".join(cleaned.split())

    @classmethod
    def extract_tokens(cls, text: str) -> List[str]:
        """Extrai tokens significativos descartando stopwords e palavras muito curtas."""
        normalized = cls.normalize_text(text)
        tokens = [t for t in normalized.split() if t not in STOPWORDS and len(t) > 1]
        return tokens

    @classmethod
    def extract_model_codes(cls, text_norm: str) -> List[str]:
        """
        Extrai códigos de modelo numéricos ou alfanuméricos (ex: 's314', 'eps314', '2365', '4060').
        Ignora unidades comuns como 'w', 'gb', 'tb', 'hz', 'v', 'mm', 'cm', 'kg', 'ml', 'l', 'mah' quando isoladas.
        """
        tokens = text_norm.split()
        unit_suffixes = ("gb", "tb", "mb", "hz", "khz", "mhz", "ghz", "mah", "mm", "cm", "kg", "ml", "rms", "pmpo")
        codes: List[str] = []
        for i, tok in enumerate(tokens):
            if not any(c.isdigit() for c in tok) or len(tok) < 2:
                continue
            if any(tok.endswith(u) and tok[:-len(u)].isdigit() for u in unit_suffixes):
                continue
            # Ignora potências/voltagens curtas comuns como "20w", "110v", "220v", "500w"
            if (tok.endswith("w") or tok.endswith("v")) and tok[:-1].isdigit():
                continue
            codes.append(tok)
            if i > 0 and tokens[i - 1].isalpha() and 1 <= len(tokens[i - 1]) <= 3 and tokens[i - 1] not in STOPWORDS:
                codes.append(f"{tokens[i - 1]}{tok}")
        return list(dict.fromkeys(codes))

    @classmethod
    def infer_brand_token(cls, q_tokens: List[str]) -> str:
        """Infere o token de marca provável ignorando palavras genéricas de categoria."""
        for tok in q_tokens:
            if len(tok) >= 4 and tok not in GENERIC_CATEGORY_WORDS and not any(c.isdigit() for c in tok):
                return tok
        return q_tokens[0] if q_tokens else ""

    @classmethod
    def check_accessory_mismatch(cls, query_norm: str, title_norm: str) -> Tuple[bool, str]:
        """
        Retorna (True, termo) se o título contiver um termo de acessório que NÃO foi
        pesquisado pelo usuário na query original. Trata singular e plural.
        """
        title_words = set(title_norm.split())
        query_words = set(query_norm.split())

        for term in ACCESSORY_TERMS:
            norm_term = cls.normalize_text(term)
            # Se for termo composto (ex: mouse pad, dock station)
            if " " in norm_term:
                if norm_term in title_norm and norm_term not in query_norm:
                    return True, term
            else:
                # Palavra individual: verifica correspondência exata de palavra (singular e plural)
                plural = f"{norm_term}s"
                if (norm_term in title_words or plural in title_words):
                    if norm_term not in query_words and plural not in query_words:
                        return True, term

        return False, ""

    @classmethod
    def check_version_clash(cls, query_norm: str, title_norm: str) -> bool:
        """
        Detecta conflitos graves de versão e geração de produtos.
        Ex: Usuário pediu 'PlayStation 5' e o título é 'PlayStation 4' (sem conter 5).
        Ex: Usuário pediu 'RTX 4060' e o título é 'RTX 3060'.
        Ex: Usuário pediu 'iPhone 15' e o título é 'iPhone 14'.
        """
        # PlayStation check
        if ("playstation 5" in query_norm or "ps5" in query_norm):
            if ("playstation 4" in title_norm or "ps4" in title_norm) and not ("playstation 5" in title_norm or "ps5" in title_norm):
                return True
            if ("playstation 3" in title_norm or "ps3" in title_norm):
                return True

        if ("playstation 4" in query_norm or "ps4" in query_norm) and not ("playstation 5" in query_norm or "ps5" in query_norm):
            if "playstation 5" in title_norm or "ps5" in title_norm:
                return True

        # Gerações de GPU (ex: RTX 40xx vs 30xx)
        gpu_q = re.search(r"\b(rtx|gtx)\s*(\d{4})\b", query_norm)
        if gpu_q:
            gpu_family, gpu_num = gpu_q.group(1), gpu_q.group(2)
            gpu_t = re.search(r"\b(rtx|gtx)\s*(\d{4})\b", title_norm)
            if gpu_t and gpu_t.group(2) != gpu_num:
                return True

        # iPhone generations (ex: iPhone 15 vs iPhone 14)
        iphone_q = re.search(r"\biphone\s*(\d{1,2})\b", query_norm)
        if iphone_q:
            ip_num = iphone_q.group(1)
            iphone_t = re.search(r"\biphone\s*(\d{1,2})\b", title_norm)
            if iphone_t and iphone_t.group(1) != ip_num:
                return True

        return False

    @classmethod
    def calculate_relevance(cls, query: str, title: str) -> Tuple[bool, float, str]:
        """
        Calcula pontuação de relevância (0.0 a 1.0) e decide se a oferta é aceita.
        Retorna (is_valid, score, reason).
        """
        query_norm = cls.normalize_text(query)
        title_norm = cls.normalize_text(title)

        if not query_norm or not title_norm:
            return False, 0.0, "Query ou título vazios"

        q_tokens = cls.extract_tokens(query)
        if not q_tokens:
            return False, 0.0, "Nenhum termo significativo na query"

        # 1. Filtro Anti-Acessório / Categoria divergente
        is_accessory, acc_term = cls.check_accessory_mismatch(query_norm, title_norm)
        if is_accessory:
            return False, 0.0, f"Acessório descartado ({acc_term})"

        # 1.1 Se o usuário NÃO usou "para" ou "p/" na busca:
        # Detecta títulos que contenham "... para <produto/marca/modelo>" ou "... compativel com <produto>"
        q_words = set(query_norm.split())
        if "para" not in q_words and "p" not in q_words:
            target_terms = [q_tokens[0]]
            if len(q_tokens) >= 2:
                target_terms.append(f"{q_tokens[0]} {q_tokens[1]}")
            if len(q_tokens) >= 3:
                target_terms.append(" ".join(q_tokens[:3]))
                target_terms.append(" ".join(q_tokens))

            for tt in target_terms:
                norm_tt = cls.normalize_text(tt)
                if (
                    f"para {norm_tt}" in title_norm
                    or f"p {norm_tt}" in title_norm
                    or f"compativel {norm_tt}" in title_norm
                    or f"compativel com {norm_tt}" in title_norm
                ):
                    return False, 0.0, f"Acessório/complemento fabricado 'para {tt}'"

        # 2. Filtro Anti-Conflito de Geração / Versão
        if cls.check_version_clash(query_norm, title_norm):
            return False, 0.0, "Conflito de versão ou geração incompatível"

        # 3. Verificação de Marca / Termo Principal Obrigatório
        # Infere a marca ignorando palavras genéricas de categoria (ex: 'caixa', 'som', 'bluetooth')
        primary_brand = cls.infer_brand_token(q_tokens)
        if len(primary_brand) >= 4 and primary_brand not in title_norm:
            # Caso especial de abreviações: ps5 -> playstation 5
            if not (primary_brand == "ps5" and "playstation" in title_norm):
                return False, 0.0, f"Marca ou termo principal obrigatório '{primary_brand}' ausente no produto"

        # 4. Cálculo de Cobertura de Tokens
        matched_tokens = 0
        title_words = set(title_norm.split())

        title_compact = title_norm.replace(" ", "")

        for token in q_tokens:
            if token in title_words or token in title_norm:
                matched_tokens += 1
            elif token.isdigit() and token in title_norm:
                matched_tokens += 1

        coverage = matched_tokens / len(q_tokens)

        # Bônus para sequência exata de modelo (ex: 'dr 500' ou 'dr500' ou 'slim')
        model_bonus = 0.0
        if len(q_tokens) >= 2:
            model_fragment = " ".join(q_tokens[1:])
            compact_model = "".join(q_tokens[1:])
            if model_fragment in title_norm or compact_model in title_compact:
                model_bonus = 0.25

        score = min(1.0, coverage + model_bonus)

        # Regra de corte
        if len(q_tokens) <= 3:
            is_valid = (coverage >= 0.66) or (coverage >= 0.5 and model_bonus > 0)
        else:
            is_valid = coverage >= 0.50

        # 5. Verificação estrita para códigos de modelo (numéricos e alfanuméricos, ex: 's314', 'eps314', '4060')
        query_codes = cls.extract_model_codes(query_norm)
        if query_codes:
            base_codes = [c for c in query_codes if any(tok == c for tok in query_norm.split())]
            for code in (base_codes or query_codes):
                # Aceita o código isolado ou sua forma concatenada (ex: 's314' ou 'eps314')
                code_present = (
                    code in title_words
                    or code in title_norm
                    or code in title_compact
                )
                if not code_present:
                    title_codes = cls.extract_model_codes(title_norm)
                    if title_codes:
                        return False, round(score * 0.4, 2), f"Modelo divergente: esperado '{code}', encontrado '{title_codes[0]}'"
                    return False, round(score * 0.5, 2), f"Código de modelo '{code}' ausente no produto"

        reason = "Aprovado pelo filtro de relevância" if is_valid else f"Baixa correspondência ({score:.0%})"
        return is_valid, score, reason

    @classmethod
    def filter_and_classify_offers(
        cls,
        query: str,
        offers: List[ProductOffer]
    ) -> Dict[str, Any]:
        """
        Filtra as ofertas aplicando regras de relevância estritas.
        Também identifica produtos alternativos da mesma marca se o modelo exato não for encontrado.
        """
        valid_offers: List[ProductOffer] = []
        rejected_offers: List[Dict[str, Any]] = []
        brand_alternatives: List[ProductOffer] = []

        q_tokens = cls.extract_tokens(query)
        primary_brand = cls.infer_brand_token(q_tokens)
        query_norm = cls.normalize_text(query)

        for offer in offers:
            if not offer or offer.price <= 0:
                continue

            is_valid, score, reason = cls.calculate_relevance(query, offer.title)
            if is_valid:
                valid_offers.append(offer)
            else:
                rejected_offers.append({
                    "title": offer.title,
                    "price": offer.price,
                    "store": offer.store,
                    "score": score,
                    "reason": reason
                })

                # Se foi rejeitado por número de modelo diferente, mas É da mesma marca e NÃO é acessório:
                norm_title = cls.normalize_text(offer.title)
                is_acc, _ = cls.check_accessory_mismatch(query_norm, norm_title)
                if (
                    primary_brand
                    and len(primary_brand) >= 4
                    and primary_brand in norm_title
                    and not is_acc
                ):
                    # Produto alternativo legítimo da mesma marca!
                    brand_alternatives.append(offer)

        # Ordena ofertas válidas pelo menor preço
        valid_offers.sort(key=lambda x: x.price)

        # Ordena alternativas de marca pelo preço e deduplica por título
        seen_alt = set()
        deduped_alts: List[ProductOffer] = []
        for alt in sorted(brand_alternatives, key=lambda x: x.price):
            norm_t = cls.normalize_text(alt.title)[:30]
            if norm_t not in seen_alt:
                seen_alt.add(norm_t)
                deduped_alts.append(alt)

        return {
            "valid_offers": valid_offers,
            "brand_alternatives": deduped_alts[:6],
            "rejected_count": len(rejected_offers),
            "rejections": rejected_offers
        }
