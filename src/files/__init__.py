import os
import re

from PIL import Image
import imagehash


_PHASH_CACHE = {}
_DUPLICATE_SUFFIX_RE = re.compile(r"^(.*?)(_\d+)?(\.[^.]*)?$")


def _file_hash(path):
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cache_key = (path, mtime)
    if cache_key not in _PHASH_CACHE:
        try:
            with Image.open(path) as image:
                _PHASH_CACHE[cache_key] = imagehash.phash(image)
        except (OSError, ValueError):
            return None
    return _PHASH_CACHE[cache_key]


def _base_image_name(filename):
    match = _DUPLICATE_SUFFIX_RE.match(filename)
    if not match:
        return None
    return match.group(1) + (match.group(3) or "")


def is_duplicate_file(folder_path, filename):
    if not os.path.isdir(folder_path):
        return False

    base_name = _base_image_name(filename)
    if base_name is None:
        return False

    for existing_file in os.listdir(folder_path):
        if existing_file != filename and _base_image_name(existing_file) == base_name:
            return True
    return False


def _remove_png_file(file_path):
    try:
        os.remove(file_path)
        print(f"Deleted: {file_path}")
    except OSError as error:
        print(f"Failed to delete {file_path}. Reason: {error}")


def remove_png():
    for asset_type in ("shirts", "pants", "temp"):
        folder_path = os.path.join("src", "assets", asset_type)
        for root, _dirs, files in os.walk(folder_path):
            for file in files:
                if file.endswith(".png"):
                    _remove_png_file(os.path.join(root, file))


def _is_image_file(filename):
    return filename.lower().endswith((".png", ".jpg", ".jpeg"))


def is_similar(new_image_path, folder_path, threshold=1):
    folder_path = {"classicshirts": "src/assets/shirts", "classicpants": "src/assets/pants"}[folder_path]
    if not os.path.isdir(folder_path):
        return False

    new_image_hash = _file_hash(new_image_path)
    if new_image_hash is None:
        return False

    new_image_name = os.path.basename(new_image_path)
    for filename in os.listdir(folder_path):
        image_path = os.path.join(folder_path, filename)
        if filename == new_image_name or not _is_image_file(filename) or not os.path.isfile(image_path):
            continue
        folder_image_hash = _file_hash(image_path)
        if folder_image_hash is None:
            continue
        if new_image_hash - folder_image_hash < threshold:
            print(f"{new_image_name} duped by {filename}")
            return True
    return False
