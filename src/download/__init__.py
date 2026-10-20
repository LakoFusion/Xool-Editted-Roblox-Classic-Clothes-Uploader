import os
import random
import re

import requests
import opennsfw2 as n2

from PIL import Image


REQUEST_TIMEOUT = 15
_ASSET_ID_RE = re.compile(r"<url>https?://www\.roblox\.com/asset/\?id=(\d+)</url>")


def _remove_quietly(path):
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _extract_asset_id(asset_xml):
    match = _ASSET_ID_RE.search(asset_xml)
    return match.group(1) if match else None


def _fetch_asset_location(cookie, asset_id):
    response = requests.get(
        f"https://assetdelivery.roblox.com/v1/assetId/{asset_id}",
        cookies={".ROBLOSECURITY": cookie.cookie},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("IsCopyrightProtected"):
        print(f"Copyright Protected! ID: {asset_id}")
        return None
    return data.get("location")


def _fetch_location_content(cookie, asset_id, as_text=False):
    try:
        location = _fetch_asset_location(cookie, asset_id)
        if not location:
            return None
        response = requests.get(location, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text if as_text else response.content
    except requests.RequestException as error:
        print(f"Error: {error}")
        return None


def get_asset_id(cookie, clothing_id):
    asset_xml = _fetch_location_content(cookie, clothing_id, as_text=True)
    return _extract_asset_id(asset_xml) if asset_xml else None


def get_png_url(cookie, asset_id):
    return _fetch_location_content(cookie, asset_id)


def replace_template(path):
    temp_marker = os.path.join("src", "assets", "temp") + os.sep
    asset_marker = os.path.join("src", "assets") + os.sep
    output_path = path.replace(temp_marker, asset_marker, 1)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with Image.open(path) as image, Image.open("src/assets/template/template.png") as template:
        base_image = image.convert("RGBA")
        template_image = template.convert("RGBA")
        base_image.paste(template_image, (0, 0), mask=template_image)
        base_image.save(output_path)
    os.remove(path)
    return output_path


def _write_temp_png(content, asset_name, temp_folder):
    path = os.path.join(temp_folder, f"{asset_name}_{random.randint(0, 100)}.png")
    with open(path, "wb") as png_file:
        png_file.write(content)
    return path


def _download_thumbnail(clothing_id, asset_name, temp_folder):
    thumbnail = get_thumbnail(clothing_id)
    if not thumbnail:
        print("Failed to download asset thumbnail")
        return None
    return _write_temp_png(thumbnail, asset_name, temp_folder)


def save_asset(cookie, clothing_id, asset_type, asset_name, max_score, path_2):
    temp_folder = os.path.join(path_2, "src", "assets", "temp", asset_type)
    os.makedirs(temp_folder, exist_ok=True)
    thumbnail_path = None
    png_path = None
    try:
        thumbnail_path = _download_thumbnail(clothing_id, asset_name, temp_folder)
        if not thumbnail_path:
            return False

        if n2.predict_image(thumbnail_path) > max_score:
            print("asset failed to pass nudity check")
            print(clothing_id)
            return False

        asset_id = get_asset_id(cookie, clothing_id)
        if not asset_id:
            print("Failed to scrape asset item id")
            return False

        png = get_png_url(cookie, asset_id)
        if not png:
            print("Failed to download asset png")
            return False

        png_path = _write_temp_png(png, asset_name, temp_folder)
        output_path = replace_template(png_path)
        print("downloaded one asset")
        return output_path
    except Exception as error:
        print(f"ERROR: {error}")
        return False
    finally:
        _remove_quietly(thumbnail_path)
        _remove_quietly(png_path)


def get_thumbnail(asset_id):
    response = requests.post(
        "https://thumbnails.roblox.com/v1/batch",
        json=[{
            "format": "png",
            "requestId": f"{asset_id}::Asset:420x420:png:regular",
            "size": "420x420",
            "targetId": asset_id,
            "token": "",
            "type": "Asset",
        }],
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json().get("data") or []
    if not data:
        return None
    image_url = data[0].get("imageUrl")
    if not image_url:
        print(f"Thumbnail not available yet for asset {asset_id}")
        return None
    image_response = requests.get(image_url, timeout=REQUEST_TIMEOUT)
    image_response.raise_for_status()
    return image_response.content
