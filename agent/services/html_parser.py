"""
HTML parser cho trường html_desc của BurgerPrints product
Trích xuất: location, material, print_method, processing_time
"""
import re
from bs4 import BeautifulSoup


# Mapping chuẩn hóa location
LOCATION_MAP = {
    "us": "US", "usa": "US", "united states": "US", "america": "US",
    "eu": "EU", "europe": "EU", "poland": "EU", "germany": "EU", "netherlands": "EU",
    "uk": "EU", "united kingdom": "EU",
    "china": "China", "vietnam": "Vietnam", "vn": "Vietnam",
}

# Mapping print method
PRINT_MAP = {
    "dtg": "DTG", "direct to garment": "DTG",
    "sublimation": "Sublimation", "dye sublimation": "Sublimation",
    "hot transfer": "Hot-Transfer", "hot-transfer": "Hot-Transfer",
    "embroidery": "Embroidery",
    "screen print": "Screen Print", "screen printing": "Screen Print",
    "aop": "AOP", "all over print": "AOP",
    "uv print": "UV Print",
}


def parse_html_desc(html_desc: str) -> dict:
    """
    Parse html_desc của BurgerPrints product.
    Returns dict với keys: location, material, print_method, processing_time, processing_min, processing_max
    """
    if not html_desc:
        return _empty_parsed()

    soup = BeautifulSoup(html_desc, "html.parser")
    text = soup.get_text(separator=" ", strip=True).lower()

    return {
        "location": _extract_location(text),
        "material": _extract_material(text),
        "print_method": _extract_print_method(text),
        "processing_time": _extract_processing_time(text),
        "processing_min": _extract_processing_min(text),
        "processing_max": _extract_processing_max(text),
    }


def _empty_parsed() -> dict:
    return {
        "location": "Unknown",
        "material": "Unknown",
        "print_method": "Unknown",
        "processing_time": "Unknown",
        "processing_min": 999,
        "processing_max": 999,
    }


def _extract_location(text: str) -> str:
    # Pattern 1: "Manufactured in United States / Poland / China..."
    m = re.search(r"manufactured\s+in\s+([a-z\s,]+?)(?:\.|$)", text)
    if m:
        raw = m.group(1).strip().rstrip(".")
        # Normalize
        raw_upper = raw.upper()
        if "UNITED STATES" in raw_upper or "USA" in raw_upper or "US" == raw_upper:
            return "US"
        if "POLAND" in raw_upper or "GERMANY" in raw_upper or "NETHERLANDS" in raw_upper or "EUROPE" in raw_upper:
            return "EU"
        if "CHINA" in raw_upper:
            return "China"
        if "VIETNAM" in raw_upper:
            return "Vietnam"
        return raw.title()

    # Pattern 2: "location: xxx"
    m = re.search(r"location[:\s]+([a-z\s]+?)(?:\s*[,\.\|]|$)", text)
    if m:
        raw = m.group(1).strip()
        for key, val in LOCATION_MAP.items():
            if key in raw:
                return val
        return raw.title()

    # Pattern 3: "fulfilled in / ships from"
    for pat in [
        r"fulfilled?\s+(?:in|from|at)\s+([a-z\s]+?)(?:\s*[,\.\|]|$)",
        r"ships?\s+from\s+([a-z\s]+?)(?:\s*[,\.\|]|$)",
        r"warehouse[:\s]+([a-z\s]+?)(?:\s*[,\.\|]|$)",
    ]:
        m = re.search(pat, text)
        if m:
            raw = m.group(1).strip()
            for key, val in LOCATION_MAP.items():
                if key in raw:
                    return val
            return raw.title()

    # Fallback: tìm tên quốc gia/khu vực trực tiếp
    for key, val in LOCATION_MAP.items():
        if re.search(r"\b" + re.escape(key) + r"\b", text):
            return val

    return "Unknown"


def _extract_material(text: str) -> str:
    # Pattern: "100% cotton" hoặc "50/50 cotton/polyester"
    patterns = [
        r"(\d+(?:\.\d+)?%\s*(?:cotton|polyester|spandex|nylon|bamboo|modal|rayon|viscose)(?:[,\s]+\d+%\s*\w+)*)",
        r"(\d+/\d+\s*cotton/polyester)",
        r"material[:\s]+([^\.\|]+?)(?:\s*[,\.\|]|$)",
        r"fabric[:\s]+([^\.\|]+?)(?:\s*[,\.\|]|$)",
    ]
    # Ưu tiên "100% cotton" hoặc "100% polyester"
    m = re.search(r"(100%\s*(?:cotton|polyester|nylon))", text)
    if m:
        return m.group(1).strip().title()
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip().title()
    return "Unknown"


def _extract_print_method(text: str) -> str:
    # Pattern thực tế của BurgerPrints: "Printing technology: Available with DTG and DTF printing"
    m = re.search(r"printing\s+technology[:\s]+([^\.\n]+)", text)
    if m:
        tech_text = m.group(1).lower()
        if "dtg" in tech_text and "dtf" in tech_text:
            return "DTG/DTF"
        if "dtg" in tech_text:
            return "DTG"
        if "dtf" in tech_text:
            return "DTF"
        if "sublimation" in tech_text:
            return "Sublimation"
        if "hot" in tech_text and "transfer" in tech_text:
            return "Hot-Transfer"
        if "aop" in tech_text:
            return "AOP"

    # Fallback: scan toàn bộ text
    for key, val in PRINT_MAP.items():
        if re.search(r"\b" + re.escape(key) + r"\b", text):
            return val

    return "Unknown"


def _extract_processing_time(text: str) -> str:
    patterns = [
        r"processing\s*time[:\s]+(\d+[-–]\d+\s*business\s*days?)",
        r"production\s*time[:\s]+(\d+[-–]\d+\s*(?:business\s*)?days?)",
        r"lead\s*time[:\s]+(\d+[-–]\d+\s*(?:business\s*)?days?)",
        r"fulfillment[:\s]+(\d+[-–]\d+\s*(?:business\s*)?days?)",
        # Pattern đơn giản hơn
        r"(\d+[-–]\d+)\s*business\s*days?",
        r"within\s+(\d+)\s*(?:business\s*)?days?",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    return "Unknown"




def _extract_processing_min(text: str) -> int:
    m = re.search(r"(\d+)[-–](\d+)\s*(?:business\s*)?days?", text)
    if m:
        return int(m.group(1))
    return 999


def _extract_processing_max(text: str) -> int:
    m = re.search(r"(\d+)[-–](\d+)\s*(?:business\s*)?days?", text)
    if m:
        return int(m.group(2))
    return 999


def normalize_product(product: dict) -> dict:
    """
    Nhận raw product dict từ BurgerPrints API,
    trả về product đã được normalize với parsed html_desc.
    Actual fields: short_code, name, html_desc, desc, url, design_type, design_url
    """
    html_desc = product.get("html_desc", "") or product.get("description", "") or ""
    parsed = parse_html_desc(html_desc)

    short_code = product.get("short_code", "")

    # Fallback: nếu không parse được processing_time, dùng default theo location
    if parsed["processing_time"] == "Unknown":
        loc = parsed["location"]
        if loc == "US":
            parsed["processing_time"] = "2-5 business days"
            parsed["processing_min"] = 2
            parsed["processing_max"] = 5
        elif loc == "EU":
            parsed["processing_time"] = "3-7 business days"
            parsed["processing_min"] = 3
            parsed["processing_max"] = 7
        elif loc == "China":
            parsed["processing_time"] = "5-10 business days"
            parsed["processing_min"] = 5
            parsed["processing_max"] = 10
        elif loc == "Vietnam":
            parsed["processing_time"] = "4-8 business days"
            parsed["processing_min"] = 4
            parsed["processing_max"] = 8

    return {
        "id": short_code,               # short_code là ID duy nhất (VD: USG5000)
        "name": product.get("name", ""),
        "short_code": short_code,
        "desc": product.get("desc", ""),  # mô tả ngắn (VD: "Budget friendly")
        "base_cost": product.get("base_cost") or product.get("price", 0),
        "currency": product.get("currency", "USD"),
        "thumbnail": product.get("url", "") or product.get("thumbnail", "") or product.get("image", ""),
        "design_type": product.get("design_type", ""),
        "status": product.get("status", "active"),
        **parsed,
        "_raw": product,
    }


