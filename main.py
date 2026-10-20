import json
import logging
import os
import random
import re
import time
import traceback

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

import tensorflow

import src


tensorflow.get_logger().setLevel(logging.FATAL)


class xool:
    current_directory = os.getcwd()
    types = ["classicshirts", "classicpants"]

    @property
    def console(self):
        if "_console" not in self.__dict__:
            self.__dict__["_console"] = src.ui.ConsoleUI()
        return self.__dict__["_console"]

    @console.setter
    def console(self, value):
        self.__dict__["_console"] = value

    def __init__(self, config, ai_settings=None, console=None):
        self.config = config
        ai = dict(config)
        ai.update(ai_settings or {})
        self.enhance_clothes = bool(ai.get("enhance_clothes", False))
        self.console = console if console is not None else src.ui.ConsoleUI()
        groups = config.get("groups") or {}
        group_ids = []
        cookie_count = 0
        if isinstance(groups, dict):
            group_ids = [str(group_id) for group_id in groups.keys()]
            for group in groups.values():
                if not isinstance(group, dict):
                    continue
                cookies = group.get("uploader_cookies") or []
                if isinstance(cookies, list):
                    cookie_count += len(cookies)
        account = ", ".join(group_ids) if group_ids else "N/A"
        if cookie_count:
            suffix = "cookie" if cookie_count == 1 else "cookies"
            account = f"{account} | {cookie_count} {suffix}"
        provider = ai.get("enhance_provider") or "local"
        mode = f"{provider} | enhance {'on' if self.enhance_clothes else 'off'}"
        self.console.set_identity(
            account=account,
            target=config.get("searching_tags", "N/A"),
            mode=mode,
        )
        try:
            initial_uploads = int(config.get("upload_amount", 0) or 0)
        except (TypeError, ValueError):
            initial_uploads = 0
        self.console.set_metric("remaining", initial_uploads)
        self.sale_pending_file = self._resolve_path(
            config.get("sale_pending_file", "src/assets/pending_sales.json")
        )
        self.sale_initial_poll_seconds = int(config.get("sale_initial_poll_seconds", 90))
        self.sale_retry_interval_seconds = int(config.get("sale_retry_interval_seconds", 300))
        self.allow_user_publish_fallback = bool(config.get("allow_user_publish_fallback", False))
        src.enhance.configure(
            provider=ai.get("enhance_provider"),
            gemini_api_key=ai.get("gemini_api_key"),
            gemini_api_keys=ai.get("gemini_api_keys"),
            gemini_model=ai.get("gemini_model"),
            gemini_cookie=ai.get("gemini_cookie"),
            gemini_download_cookie=ai.get("gemini_download_cookie"),
            gemini_cookie_min_delay_seconds=ai.get("gemini_cookie_min_delay_seconds"),
            gemini_cookie_cooldown_seconds=ai.get("gemini_cookie_cooldown_seconds"),
            gemini_cookie_max_strategies=ai.get("gemini_cookie_max_strategies"),
            max_nudity_value=config.get("max_nudity_value", 0.08),
            replicate_api_token=ai.get("replicate_api_token"),
            sd_model_version=ai.get("sd_model_version"),
            sd_prompt_strength=ai.get("sd_prompt_strength"),
            use_controlnet=ai.get("use_controlnet"),
        )

        if config.get("delete_all_images_on_restart"):
            src.files.remove_png()

        for group_id, group_config in config.get("groups", {}).items():
            for cookie in group_config.get("uploader_cookies", []):
                self.upload(cookie, group_id)

    def _asset_folder(self, current_type):
        return "shirts" if current_type == "classicshirts" else "pants"

    def _upload_asset_type(self, current_type):
        return "shirt" if current_type == "classicshirts" else "pants"

    def _resolve_path(self, path):
        return path if os.path.isabs(path) else os.path.join(self.current_directory, path)

    def _search_tags(self):
        return self.config.get("searching_tags", "")

    def _required_tags(self):
        return [
            tag.lower()
            for tag in re.split(r"[\s,]+", self._search_tags())
            if tag.strip()
        ]

    def _has_required_tag(self, item_name, path):
        required_tags = self._required_tags()
        if not required_tags:
            return True

        text = f"{item_name} {os.path.basename(path)}".lower()
        words = set(re.findall(r"\w+", text))
        return any(tag in words for tag in required_tags)

    @staticmethod
    def _remove_quietly(path):
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _load_pending_sales(self):
        if not os.path.exists(self.sale_pending_file):
            return []
        try:
            with open(self.sale_pending_file, "r", encoding="utf-8") as pending_file:
                data = json.load(pending_file)
        except (OSError, json.JSONDecodeError) as error:
            print(f"[sale] could not read pending sales file: {error}")
            return []
        return data if isinstance(data, list) else []

    def _save_pending_sales(self, entries):
        directory = os.path.dirname(self.sale_pending_file) or "."
        os.makedirs(directory, exist_ok=True)
        temp_path = f"{self.sale_pending_file}.tmp"
        with open(temp_path, "w", encoding="utf-8") as pending_file:
            json.dump(entries, pending_file, indent=2, ensure_ascii=False)
        os.replace(temp_path, self.sale_pending_file)
        self.console.set_metric("pending", len(entries))

    def _add_pending_sale(self, entry):
        pending = self._load_pending_sales()
        key = (str(entry.get("group_id")), str(entry.get("asset_id")))
        for index, existing in enumerate(pending):
            existing_key = (str(existing.get("group_id")), str(existing.get("asset_id")))
            if existing_key == key:
                entry["created_at"] = existing.get("created_at", entry.get("created_at"))
                pending[index] = entry
                break
        else:
            pending.append(entry)
        self._save_pending_sales(pending)

    def _queue_pending_sale(self, asset_id, item_name, description, group_id, asset_type, result):
        now = time.time()
        self._add_pending_sale({
            "asset_id": int(asset_id),
            "name": str(item_name)[:50],
            "description": description,
            "group_id": str(group_id),
            "asset_type": asset_type,
            "price": int(self.config.get("assets_price", 5)),
            "created_at": now,
            "last_attempt_at": now,
            "attempts": max(1, int(result.get("attempts") or 0)),
            "last_status": result.get("last_status") or result.get("status"),
            "last_reason": result.get("reason"),
        })
        print(f"[sale] queued asset {asset_id} for later sale retry: {result.get('reason')}")

    def _retry_pending_entry(self, entry, cookie, group_id, now, force):
        asset_id = entry.get("asset_id")
        if not asset_id:
            return False, True

        last_attempt = float(entry.get("last_attempt_at") or 0)
        if not force and now - last_attempt < self.sale_retry_interval_seconds:
            return True, False

        print(f"[sale] retrying pending asset {asset_id}...")
        entry["last_attempt_at"] = now
        entry["attempts"] = int(entry.get("attempts") or 0) + 1
        result = src.upload.release_asset(
            cookie,
            asset_id,
            entry.get("price", self.config.get("assets_price", 5)),
            entry.get("name", ""),
            entry.get("description", self.config.get("description", "")),
            group_id,
            initial_poll_seconds=0,
            allow_user_publish_fallback=self.allow_user_publish_fallback,
        )
        if result.get("ok"):
            print(f"[sale] pending asset sold. ID {asset_id}")
            return False, True
        if result.get("terminal") and not result.get("queue"):
            print(f"[sale] pending asset removed. ID {asset_id} | {result.get('reason')}")
            return False, True

        entry["last_status"] = result.get("status")
        entry["last_reason"] = result.get("reason")
        print(f"[sale] pending asset still waiting. ID {asset_id} | {result.get('reason')}")
        return True, True

    def retry_pending_sales(self, cookie, group_id, force=False):
        pending = self._load_pending_sales()
        self.console.set_metric("pending", len(pending))
        if not pending:
            return

        now = time.time()
        changed = False
        remaining = []
        for entry in pending:
            if str(entry.get("group_id")) != str(group_id):
                remaining.append(entry)
                continue

            keep, entry_changed = self._retry_pending_entry(entry, cookie, group_id, now, force)
            changed = changed or entry_changed
            if keep:
                remaining.append(entry)

        if changed:
            self._save_pending_sales(remaining)

    def _pick_candidates(self, cookie, current_type):
        items = src.scrape.scrape_assets(cookie, self._search_tags(), current_type)
        random.shuffle(items)
        candidates = src.scrape.sort_assets(
            cookie,
            items[:40],  # Wider pool per round reduces starvation after shuffling.
            self.config.get("blacklisted_creators", []),
            self.config.get("blacklisted_words", []),
            self.config.get("upload_without_blacklisted_words", True),
        )
        for candidate in candidates:
            candidate["name"] = src.naming.to_english(candidate.get("name"))
        self.console.set_metric("candidates", len(candidates))
        self.console.log(f"scan {current_type}: {len(candidates)} candidate(s)")
        return candidates

    def _process_asset(self, item, current_type, asset_folder, cookie, group_id):
        duplicate_name = f"{item['name']}_{random.randint(0, 100)}.png"
        asset_path = os.path.join(self.current_directory, "src", "assets", asset_folder)
        if self.config.get("dupe_check", True) and src.files.is_duplicate_file(asset_path, duplicate_name):
            print(f"DUPE skipping: {item['name']}")
            self.console.incr_metric("skipped")
            return "skip"

        if self.config.get("require_one_tag_in_name", False) and not self._has_required_tag(item["name"], duplicate_name):
            print(f"No required tag found skipping: {item['name']}")
            self.console.incr_metric("skipped")
            return "skip"

        path = src.download.save_asset(
            cookie,
            item["id"],
            asset_folder,
            item["name"],
            self.config.get("max_nudity_value", 0.1),
            self.current_directory,
        )
        if not path:
            print(f"No path found skipping: {item['name']}")
            self.console.incr_metric("skipped")
            return "skip"

        if self.config.get("dupe_check", True) and src.files.is_similar(path, current_type):
            print(f"Found similar clothe skipping: {item['name']}")
            self._remove_quietly(path)
            self.console.incr_metric("skipped")
            return "skip"

        if self.enhance_clothes:
            src.enhance.enhance_clothing(path, item["name"], self._search_tags())

        item_uploaded = src.upload.create_asset(
            item["name"],
            path,
            self._upload_asset_type(current_type),
            cookie,
            group_id,
            self.config.get("description", ""),
            5,
            5,
        )
        if item_uploaded is False:
            print(f"Failed to upload skipping: {item['name']}")
            self.console.incr_metric("failed")
            return "skip"
        if item_uploaded == 2:
            print(f"Failed to upload (not enough funds), stopping: {item['name']}")
            self.console.incr_metric("failed")
            return "stop"
        if item_uploaded == 3:
            print(f"Failed to upload (no permission), stopping: {item['name']}")
            self.console.incr_metric("failed")
            return "stop"

        asset_id = (item_uploaded.get("response") or {}).get("assetId")
        if not asset_id:
            print(f"Upload missing assetId skipping: {item['name']}")
            self.console.incr_metric("failed")
            return "skip"

        sale_result = src.upload.release_asset(
            cookie,
            asset_id,
            self.config.get("assets_price", 5),
            item["name"],
            self.config.get("description", ""),
            group_id,
            initial_poll_seconds=self.sale_initial_poll_seconds,
            allow_user_publish_fallback=self.allow_user_publish_fallback,
        )
        if sale_result.get("ok"):
            print(f"Released item. ID {asset_id}")
            self.console.incr_metric("uploaded")
            return "done"
        if sale_result.get("queue"):
            self._queue_pending_sale(
                asset_id,
                item["name"],
                self.config.get("description", ""),
                group_id,
                self._upload_asset_type(current_type),
                sale_result,
            )
            self.console.incr_metric("uploaded")
            return "done"

        print(f"Failed to release item. ID {asset_id} | {sale_result.get('reason')}")
        self._queue_pending_sale(
            asset_id,
            item["name"],
            self.config.get("description", ""),
            group_id,
            self._upload_asset_type(current_type),
            {
                **sale_result,
                "last_status": sale_result.get("last_status") or "release_failed",
                "attempts": sale_result.get("attempts", 0),
            },
        )
        self.console.incr_metric("failed")
        return "skip"

    def upload(self, cookie, group_id):
        if not cookie:
            raise Exception("Empty cookie")

        try:
            cookie = src.cookie.cookie(cookie)
        except Exception as error:
            print(f"[upload] skipping cookie: {error}")
            self.console.incr_metric("failed")
            return
        self.console.set_status("Running")
        self.console.set_identity(account=f"group {group_id}")
        self.retry_pending_sales(cookie, group_id, force=True)

        remaining_uploads = int(self.config.get("upload_amount", 0))
        self.console.set_metric("remaining", remaining_uploads)
        self.console.set_metric("round", 0)
        if remaining_uploads <= 0:
            print("upload_amount is 0; nothing to upload.")
            return

        empty_rounds = 0
        crash_rounds = 0
        stop_requested = False
        sleep_seconds = max(0.0, float(self.config.get("sleep_each_upload") or 1))
        while remaining_uploads > 0 and not stop_requested:
            uploads_before = remaining_uploads
            round_failed = False
            self.console.incr_metric("round")
            try:
                self.retry_pending_sales(cookie, group_id)
                current_type = random.choice(self.types)
                asset_folder = self._asset_folder(current_type)

                for item in self._pick_candidates(cookie, current_type):
                    if remaining_uploads <= 0:
                        break
                    outcome = self._process_asset(item, current_type, asset_folder, cookie, group_id)
                    if outcome == "stop":
                        return
                    if outcome == "done":
                        remaining_uploads -= 1
                        self.console.set_metric("remaining", remaining_uploads)
                    if remaining_uploads <= 0:
                        break
                    if outcome in ("done", "skip"):
                        time.sleep(sleep_seconds)
                crash_rounds = 0
            except Exception as e:
                round_failed = True
                crash_rounds += 1
                if crash_rounds >= 10:
                    print("10 consecutive failed rounds; stopping uploads for this cookie.")
                    stop_requested = True
                if str(e) == "403":
                    print("403: Could mean invalid cookie.")
                    cookie.generate_token()
                    continue
                print(f"ERROR: {traceback.format_exc()}")
                self.console.incr_metric("failed")
            finally:
                if remaining_uploads < uploads_before:
                    empty_rounds = 0
                    crash_rounds = 0
                elif not round_failed:
                    empty_rounds += 1
                    if empty_rounds >= 10:
                        print("No progress after 10 rounds; stopping uploads for this cookie.")
                        stop_requested = True


if __name__ == "__main__":
    with open("config.json", "r", encoding="utf-8") as config_file:
        config = json.loads(config_file.read())
    ai_settings = {}
    if os.path.exists("ai_settings.json"):
        with open("ai_settings.json", "r", encoding="utf-8") as ai_file:
            ai_settings = json.loads(ai_file.read())
    console = src.ui.ConsoleUI(tool_name="Clothes Uploader Roblox", version="1.0")
    try:
        console.start()
        xool(config, ai_settings, console)
    finally:
        console.stop()
