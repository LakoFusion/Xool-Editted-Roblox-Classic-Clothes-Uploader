import json
import re
import time
import uuid

from requests_toolbelt.multipart.encoder import MultipartEncoder


REQUEST_TIMEOUT = 20
EXPECTED_UPLOAD_PRICE = 80
DEFAULT_PUBLISHING_ADVANCE = 10
TARGET_TYPE_ASSET = 0
PUBLISHING_TYPE_MARKETPLACE = 2
SALE_LOCATION_CATALOG = 1
RESALE_RESTRICTION_NONE = 2
PUBLISHABLE_STATUSES = {"ReviewApproved", "OffSale"}
TERMINAL_REJECTED_STATUSES = {"Moderated"}


def _safe_json(response):
    if response is None:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _response_sample(response):
    if response is None:
        return "no response"
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    return json.dumps(body)[:500]


def _publish_error_is_retryable(response):
    text = str(response.text or "").lower()
    if "gateway could not publish" in text:
        return True
    compact = text.replace(" ", "")
    return '"code":32' in compact or '"code":"32"' in compact


def _request(method, url, cookie, retries=3, **kwargs):
    return cookie.request(method, url, retries=retries, timeout=REQUEST_TIMEOUT, **kwargs)


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def create_asset(name, path, asset_type, cookie, group_id, description, _total_tries, wait_time):
    gid = str(group_id)
    if not group_id or gid.strip() in ("", "0", "None"):
        user_id = getattr(cookie, "user_id", "") or getattr(cookie, "userId", "")
        if not user_id:
            print("[upload] missing creator id")
            return False
        creator = {"userId": str(user_id)}
    else:
        creator = {"groupId": gid}
    name = str(name)[:50]
    payload = {
        "assetType": asset_type,
        "creationContext": {
            "creator": creator,
            "expectedPrice": EXPECTED_UPLOAD_PRICE
        },
        "description": description,
        "displayName": name,
    }
    with open(path, "rb") as image_file:
        multipart_data = MultipartEncoder(
            fields={
                "request": json.dumps(payload),
                "fileContent": ("test.png", image_file, "image/png")
            }
        )
        # Read the encoder once into bytes so CSRF/429 retries in
        # cookie.request can safely replay the body (MultipartEncoder is
        # one-shot: a second read returns an empty payload).
        request_body = multipart_data.read()
        content_type = multipart_data.content_type
        response = cookie.request(
            "POST",
            "https://apis.roblox.com/assets/user-auth/v1/assets",
            data=request_body,
            headers={"Content-Type": content_type},
        )
    body = _safe_json(response) or {}
    if not body.get("operationId"):
        message = body.get("message", "")
        if not message and body.get("errors"):
            message = body["errors"][0].get("message", "")
        message = str(message or "")

        print(f"[upload] create_asset failed: {message}")
        if "xsrf token invalid" in message.lower() and _total_tries > 0:
            print("[upload] Refreshing XSRF token and retrying...")
            cookie.generate_token()
            return create_asset(name, path, asset_type, cookie, group_id, description, _total_tries - 1, wait_time)

        if "insufficientfunds" in message.lower():
            match = re.search(r"(\d+)\s*Robux\s+is\s+needed", message, re.IGNORECASE)
            print(f"[upload] insufficient funds: {message}")
            if match:
                print(f"[upload] required amount: {match.group(1)} Robux")
            return 2
        if "unauthorized" in message.lower():
            return 3
        return False

    for _ in range(_total_tries):
        response = cookie.request(
            "GET",
            f"https://apis.roblox.com/assets/user-auth/v1/operations/{body['operationId']}",
        )
        poll_body = _safe_json(response) or {}
        if response is not None and response.status_code == 200 and poll_body.get("done") not in [None, False]:
            err = poll_body.get("error")
            if not err:
                return poll_body
            if isinstance(err, dict):
                message = str(err.get("message") or "")
            else:
                message = str(err)
            lowered = message.lower()
            if "insufficientfunds" in lowered or "insufficient funds" in lowered:
                print(f"[upload] insufficient funds: {message}")
                return 2
            if "unauthorized" in lowered or "permission" in lowered:
                return 3
            match = re.search(r"(\d+)\s*Robux\s+is\s+needed", message, re.IGNORECASE)
            print(f"[upload] asset creation operation error: {message}")
            if match:
                print(f"[upload] required amount: {match.group(1)} Robux")
            return False
        time.sleep(wait_time)
    return False


def get_asset_details(cookie, asset_ids):
    ids = [parsed for parsed in map(_as_int, asset_ids) if parsed is not None]
    if not ids:
        return []

    response = _request(
        "POST",
        "https://itemconfiguration.roblox.com/v1/creations/get-asset-details",
        cookie,
        json={"AssetIds": ids},
    )
    if response is None or response.status_code != 200:
        print(f"[upload] get_asset_details failed: {_response_sample(response)}")
        return []
    body = _safe_json(response)
    if body is None:
        print("[upload] get_asset_details failed: invalid JSON response")
        return []
    return body if isinstance(body, list) else []


def get_asset_detail(cookie, asset_id):
    for detail in get_asset_details(cookie, [asset_id]):
        if str(detail.get("assetId")) == str(asset_id):
            return detail
    return None


def wait_until_publishable(cookie, asset_id, max_wait_seconds=90, poll_interval=15):
    deadline = time.time() + max(0, int(max_wait_seconds or 0))
    while True:
        detail = get_asset_detail(cookie, asset_id)
        status = detail.get("status") if detail else "Unknown"
        print(f"[upload] asset {asset_id} moderation status: {status}")

        if status in PUBLISHABLE_STATUSES or status in TERMINAL_REJECTED_STATUSES or status == "OnSale":
            return detail

        if not max_wait_seconds or time.time() >= deadline:
            return detail

        wait = min(poll_interval, max(1, int(deadline - time.time())))
        print(f"[upload] waiting {wait}s for moderation...")
        time.sleep(wait)


def check_publish_access(cookie, asset_id):
    response = _request(
        "GET",
        "https://itemconfiguration.roblox.com/v1/collectibles/check-item-publish-access",
        cookie,
        params={
            "TargetType": TARGET_TYPE_ASSET,
            "TargetId": int(asset_id),
            "PublishingType": PUBLISHING_TYPE_MARKETPLACE,
        },
    )
    if response is None:
        return {"isAllowed": False, "deniedReason": "no response from Roblox"}
    if response.status_code != 200:
        return {
            "isAllowed": False,
            "deniedReason": f"HTTP {response.status_code}: {_response_sample(response)}",
        }
    body = _safe_json(response)
    if body is None:
        return {"isAllowed": False, "deniedReason": "Invalid publish access response"}
    return body


def get_price_floor(cookie, asset_id):
    response = _request(
        "GET",
        "https://itemconfiguration.roblox.com/v1/collectibles/price-floor",
        cookie,
        params={
            "TargetType": TARGET_TYPE_ASSET,
            "TargetId": int(asset_id),
            "PublishingType": PUBLISHING_TYPE_MARKETPLACE,
        },
    )
    if response is None or response.status_code != 200:
        print(f"[upload] price floor failed: {_response_sample(response)}")
        return None
    return _safe_json(response)


def get_publishing_fee(cookie, asset_id, is_free=False):
    response = _request(
        "GET",
        "https://itemconfiguration.roblox.com/v1/collectibles/publishing-fees",
        cookie,
        params={
            "TargetType": TARGET_TYPE_ASSET,
            "TargetID": int(asset_id),
            "Quantity": 0,
            "SaleLocation": SALE_LOCATION_CATALOG,
            "ResaleRestriction": RESALE_RESTRICTION_NONE,
            "IsFree": str(bool(is_free)).lower(),
            "PublishingType": PUBLISHING_TYPE_MARKETPLACE,
        },
    )
    if response is None or response.status_code != 200:
        print(f"[upload] publishing fee failed: {_response_sample(response)}")
        return None
    return _safe_json(response)


def verify_on_sale(cookie, asset_id, attempts=6, wait_time=5):
    for _ in range(attempts):
        detail = get_asset_detail(cookie, asset_id)
        status = detail.get("status") if detail else "Unknown"
        if status == "OnSale":
            return True, detail
        if status in TERMINAL_REJECTED_STATUSES:
            return False, detail
        time.sleep(wait_time)
    return False, get_asset_detail(cookie, asset_id)


def _denial_is_temporary(reason):
    text = str(reason or "").lower()
    if not text:
        return True
    return any(
        marker in text
        for marker in ("review", "moderation", "pending", "temporary", "try again", "not approved")
    ) or any(marker in text for marker in ("http 429", "http 500", "http 502", "http 503", "http 504", "flood", "rate limit"))


def _result(ok=False, status="failed", reason="", queue=False, terminal=False, **extra):
    data = {
        "ok": ok,
        "status": status,
        "reason": reason,
        "queue": queue,
        "terminal": terminal,
    }
    data.update(extra)
    return data


def _build_publish_payload(cookie, asset_id, name, description, final_price, publishing_fee, gid):
    data = {
        "saleLocationConfiguration": {"saleLocationType": SALE_LOCATION_CATALOG, "places": []},
        "targetId": int(asset_id),
        "priceInRobux": final_price,
        "publishingType": PUBLISHING_TYPE_MARKETPLACE,
        "idempotencyToken": str(uuid.uuid4()),
        "name": name,
        "description": description,
        "isFree": False,
        "agreedPublishingFee": publishing_fee,
        "priceOffset": 0,
        "quantity": 0,
        "quantityLimitPerUser": 0,
        "resaleRestriction": RESALE_RESTRICTION_NONE,
        "targetType": TARGET_TYPE_ASSET,
        "publisherUserId": cookie.user_id,
    }
    if isinstance(gid, int) and gid > 0:
        data["creatorGroupId"] = gid
    return data


def _post_collectible(cookie, data):
    return _request(
        "POST",
        "https://itemconfiguration.roblox.com/v1/collectibles",
        cookie,
        json=data,
    )


def publish_asset_for_sale(
    cookie,
    asset_id,
    price,
    name,
    description,
    group_id,
    allow_user_publish_fallback=False,
    asset_detail=None,
):
    detail = asset_detail or get_asset_detail(cookie, asset_id)
    status = detail.get("status") if detail else "Unknown"
    if status == "OnSale":
        return _result(True, "on_sale", "already on sale", terminal=True, asset_detail=detail)
    if status in TERMINAL_REJECTED_STATUSES:
        return _result(False, status.lower(), "asset was moderated", terminal=True, asset_detail=detail)
    if status not in PUBLISHABLE_STATUSES:
        return _result(False, "pending", f"asset is not approved yet ({status})", queue=True, asset_detail=detail)

    access = check_publish_access(cookie, asset_id)
    if not access.get("isAllowed"):
        reason = access.get("deniedReason", "publish access denied")
        temporary = _denial_is_temporary(reason)
        print(f"[upload] publish access denied for {asset_id}: {reason}")
        return _result(False, "denied", reason, queue=temporary, terminal=not temporary, asset_detail=detail)

    floor = get_price_floor(cookie, asset_id)
    fee = get_publishing_fee(cookie, asset_id)
    if floor is None or fee is None:
        return _result(False, "retry", "could not fetch price floor or publishing fee", queue=True, asset_detail=detail)

    try:
        desired_price = int(price)
    except (TypeError, ValueError):
        desired_price = 5
    price_floor = int(floor.get("priceFloorInRobux") or 0)
    final_price = max(desired_price, price_floor)
    publishing_fee = int(fee.get("publishingFeeInRobux") or DEFAULT_PUBLISHING_ADVANCE)

    try:
        gid = int(group_id)
    except (ValueError, TypeError):
        gid = group_id

    name = str(name)[:50]
    data = _build_publish_payload(
        cookie,
        asset_id,
        name,
        description,
        final_price,
        publishing_fee,
        gid,
    )
    response = _post_collectible(cookie, data)
    if response is None:
        return _result(
            False,
            "publish_failed",
            "no response from Roblox (network error)",
            queue=True,
            asset_detail=detail,
        )

    if (
        allow_user_publish_fallback
        and response.status_code == 400
        and "Invalid Argument" in response.text
        and "creatorGroupId" in data
    ):
        print("[upload] group publish failed; retrying without creatorGroupId because fallback is enabled")
        del data["creatorGroupId"]
        response = _post_collectible(cookie, data)
        if response is None:
            return _result(
                False,
                "publish_failed",
                "no response from Roblox (network error)",
                queue=True,
                asset_detail=detail,
            )

    if response.status_code != 200:
        print(f"[upload] publish response: HTTP {response.status_code} | {_response_sample(response)}")
        temporary = response.status_code in (429, 500, 502, 503, 504) or _publish_error_is_retryable(response)
        return _result(
            False,
            "publish_failed",
            f"HTTP {response.status_code}: {_response_sample(response)}",
            queue=temporary,
            terminal=not temporary,
            asset_detail=detail,
            price=final_price,
            publishing_fee=publishing_fee,
        )

    is_on_sale, verified_detail = verify_on_sale(cookie, asset_id)
    if is_on_sale:
        return _result(
            True,
            "on_sale",
            "published and verified",
            terminal=True,
            asset_detail=verified_detail,
            price=final_price,
            publishing_fee=publishing_fee,
        )

    verified_status = verified_detail.get("status") if verified_detail else "Unknown"
    if verified_status in TERMINAL_REJECTED_STATUSES:
        return _result(False, verified_status.lower(), "asset was moderated after publish", terminal=True)
    return _result(
        False,
        "verify_pending",
        f"publish accepted but asset is not OnSale yet ({verified_status})",
        queue=True,
        asset_detail=verified_detail,
        price=final_price,
        publishing_fee=publishing_fee,
    )


def release_asset(
    cookie,
    asset_id,
    price,
    name,
    description,
    group_id,
    initial_poll_seconds=90,
    allow_user_publish_fallback=False,
):
    detail = wait_until_publishable(cookie, asset_id, max_wait_seconds=initial_poll_seconds)
    return publish_asset_for_sale(
        cookie,
        asset_id,
        price,
        name,
        description,
        group_id,
        allow_user_publish_fallback=allow_user_publish_fallback,
        asset_detail=detail,
    )
