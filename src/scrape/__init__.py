import random
import re


def scrape_assets(cookie, keywords, subcategory):
    params = {
        "category": "Clothing",
        "limit": 120,
        "salesTypeFilter": 1,
        "sortAggregation": random.choice(["1", "3", "5"]),
        "sortType": random.randint(0, 2),
        "subcategory": subcategory,
        "minPrice": 5,
        "keyword": keywords,
    }
    item_ids = []
    seen_ids = set()
    cursor = None
    for _ in range(3):
        if cursor:
            params["cursor"] = cursor
        response = cookie.request(
            "GET",
            "https://catalog.roblox.com/v1/search/items",
            params=params,
        )
        if response is None or response.status_code != 200:
            break
        try:
            payload = response.json()
        except ValueError:
            break

        new_items = 0
        for item in payload.get("data") or []:
            item_id = item.get("id")
            if item_id is None or item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            item_ids.append(item_id)
            new_items += 1
            if len(item_ids) >= 150:
                return item_ids

        cursor = payload.get("nextPageCursor")
        if not cursor or not new_items:
            break
    return item_ids


def _clean_asset_name(raw_name, blacklisted_words, upload_without_blacklisted_words):
    """Sanitize an asset name and apply the blacklist. Returns (name, blocked)."""
    name = re.sub(r'[<>:"/\\|?*]', "_", raw_name)
    for blacklisted_word in blacklisted_words:
        if not blacklisted_word:
            continue
        if str(blacklisted_word).lower() not in name.lower():
            continue
        if not upload_without_blacklisted_words:
            return None, True
        name = re.sub(re.escape(str(blacklisted_word)), "", name, flags=re.IGNORECASE)

    return re.sub(r"\s+", " ", name.replace("/", " ")).strip(), False


def sort_assets(cookie, ids, blacklisted_creators, blacklisted_words, upload_without_blacklisted_words):
    if not ids:
        return []

    response = cookie.request(
        "POST",
        "https://catalog.roblox.com/v1/catalog/items/details",
        json={"items": [{"itemType": "Asset", "id": id} for id in ids]},
    )
    if response is None:
        return []
    if response.status_code == 403:
        raise Exception("403")
    if response.status_code == 429:
        raise Exception("Ratelimit hit. This may take a while to go away.")
    if response.status_code != 200:
        return []

    items = []
    blacklisted_creator_ids = {str(creator) for creator in blacklisted_creators}
    for item in response.json().get("data", []):
        if str(item.get("creatorTargetId")) in blacklisted_creator_ids:
            continue

        name, blocked = _clean_asset_name(
            str(item.get("name", "")),
            blacklisted_words,
            upload_without_blacklisted_words,
        )
        if blocked or not name:
            continue
        item["name"] = name
        items.append(item)
    return items
