from __future__ import annotations

import re


_VI_DIACRITICS_RE = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]")

_VI_MARKERS = {
    "toi", "muon", "can", "tim", "goi", "y", "san", "pham", "so", "sanh", "kiem", "tra",
    "ton", "kho", "chi", "tiet", "mau", "sac", "kich", "thuoc", "xuong", "partner", "gia",
    "duoi", "tren", "ngay", "thi", "truong", "my", "viet", "nam", "co", "nhung", "nao",
    "hay", "giup", "cho", "toi", "la", "voi", "va", "cua", "nay", "roi", "them",
}

_EN_MARKERS = {
    "find", "recommend", "compare", "check", "stock", "product", "products", "detail",
    "details", "color", "colors", "size", "sizes", "factory", "factories", "partner",
    "partners", "price", "shipping", "production", "days", "under", "over", "market",
    "please", "show", "list", "best", "what", "which", "how", "for", "with", "this",
    "that", "these", "those", "more", "about", "order", "create", "info", "information",
}


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", (text or "").lower())


def detect_response_language(query: str, default: str = "vi") -> str:
    text = (query or "").strip()
    if not text:
        return default

    lowered = text.lower()
    if _VI_DIACRITICS_RE.search(lowered):
        return "vi"

    tokens = _tokenize(lowered)
    if not tokens:
        return default

    vi_score = sum(1 for token in tokens if token in _VI_MARKERS)
    en_score = sum(1 for token in tokens if token in _EN_MARKERS)

    if vi_score > en_score:
        return "vi"
    if en_score > vi_score:
        return "en"

    if re.search(r"\b(what|which|under|days|show|find|compare|recommend|factory|product|products)\b", lowered):
        return "en"
    if re.search(r"\b(duoi|ngay|san|pham|so|sanh|kiem|tra|chi|tiet)\b", lowered):
        return "vi"
    return default
