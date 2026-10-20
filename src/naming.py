import re
import unicodedata

# Vietnamese-to-English lexicon for Roblox catalog clothing names.
# Keys are matched against diacritic-stripped, lowercased text, so they are
# written without accents (accented input is normalized before matching).
# Longer phrases are applied
# before single words so "quan jean" wins over bare "quan".
LEXICON = {
    # garments and garment phrases
    "quan jean": "denim jeans",
    "quan jeans": "denim jeans",
    "quan dui": "shorts",
    "quan short": "shorts",
    "quan dai": "pants",
    "quan": "pants",
    "ao thun": "t-shirt",
    "ao so mi": "button-up shirt",
    "ao khoac": "jacket",
    "ao len": "sweater",
    "ao hoodie": "hoodie",
    "ao crop top": "crop top",
    "ao croptop": "crop top",
    "ao": "shirt",
    "vay ngan": "short skirt",
    "vay dai": "long skirt",
    "vay": "skirt",
    "dam": "dress",
    "that lung": "waist",
    "tay dai": "long sleeve",
    "tay ngan": "short sleeve",
    # colors
    "mau xanh la cay": "green",
    "xanh la cay": "green",
    "xanh la": "green",
    "xanh nuoc bien": "blue",
    "xanh duong": "blue",
    "xanh ngoc": "teal",
    "xanh mint": "mint",
    "xanh": "blue",
    "mau den": "black",
    "mau trang": "white",
    "mau hong": "pink",
    "mau do": "red",
    "mau vang": "gold",
    "mau tim": "purple",
    "mau cam": "orange",
    "mau nau": "brown",
    "mau xam": "gray",
    "mau kem": "cream",
    "mau sua": "milk",
    "mau dam": "dark color",
    "hong pastel": "pastel pink",
    "hong": "pink",
    "den": "black",
    "trang": "white",
    "do": "red",
    "vang": "gold",
    "tim": "purple",
    "cam": "orange",
    "nau": "brown",
    "xam": "gray",
    "kem": "cream",
    "sua": "milk",
    "nhat": "light",
    "toi": "dark",
    "bac": "silver",
    "mau": "color",
    # prints and motifs
    "ngoi sao": "star",
    "ngoi nha": "house",
    "trai tim": "heart",
    "sao": "star",
    "hoa": "floral",
    "vuong mien": "crown",
    "cong chua": "princess",
    "hoang tu": "prince",
    "nu hoang": "queen",
    "thien than": "angel",
    "than chet": "death",
    "gau": "bear",
    "tho": "bunny",
    "meo": "cat",
    "chim": "bird",
    "rua": "turtle",
    # holidays and seasons
    "giang sinh": "christmas",
    "noel": "christmas",
    "cay thong": "christmas tree",
    "ong gia noel": "santa",
    "tuan loc": "reindeer",
    "qua tang": "gift",
    "tuyet": "snow",
    "le hoi": "festival",
    "halloween": "halloween",
    "ao dai": "ao dai",
    # style words
    "phong cach": "style",
    "co dien": "classic",
    "cot loi": "core",
    "ram": "baggy",
    "rach": "ripped",
    "vintage": "vintage",
}

_PHRASE_ORDER = sorted(LEXICON, key=len, reverse=True)
_ALLOWED_RE = re.compile(r"[^A-Za-z0-9\s\-_.,()&'!+]")


def _strip_diacritics(text):
    text = text.replace("\u0111", "d").replace("\u0110", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _apply_lexicon(text):
    for key in _PHRASE_ORDER:
        pattern = r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])"
        text = re.sub(pattern, LEXICON[key], text, flags=re.IGNORECASE)
    return text


def _titlecase_words(text):
    return re.sub(r"[A-Za-z]+", lambda match: match.group(0).capitalize(), text)


def to_english(name):
    """Normalize a scraped catalog name into an English, ASCII-safe display name."""
    text = str(name or "")
    text = _strip_diacritics(text).lower()
    text = re.sub(r"\s+", " ", text)
    text = _apply_lexicon(text)
    text = _ALLOWED_RE.sub(" ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    text = re.sub(r"\s+", " ", text).strip(" ,-.")
    if not text:
        return "item"
    return _titlecase_words(text)


def is_english(name):
    text = str(name or "")
    return bool(text) and not _ALLOWED_RE.search(text)
