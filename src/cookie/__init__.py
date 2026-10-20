import time

import requests


REQUEST_TIMEOUT = 15
CSRF_REFRESH_AFTER = 120
_CSRF_MARKERS = ("token validation failed", "xsrf", "csrf")


def _backoff_seconds(attempt, cap):
    return min(2 ** attempt, cap)


def _is_csrf_rejection(response):
    if response.status_code != 403:
        return False
    body_lower = response.text.lower()
    return any(marker in body_lower for marker in _CSRF_MARKERS)


class cookie:
    def __init__(self, cookie):
        self.cookie = cookie
        self._x_token = None
        self.last_generated_time = 0
        self.user_id = None
        self.session = requests.Session()
        self.session.cookies.set(".ROBLOSECURITY", cookie, domain=".roblox.com")
        self.generate_token()
        self.get_user_id()

    def generate_token(self):
        try:
            response = self.session.post(
                "https://auth.roblox.com/v2/logout",
                timeout=REQUEST_TIMEOUT,
            )
            self._x_token = response.headers.get("x-csrf-token")
        except requests.RequestException as error:
            print(f"[cookie] could not refresh CSRF token: {error}")
            self._x_token = None
        self.last_generated_time = time.time()
        return self._x_token

    def x_token(self):
        if self._x_token is None or time.time() - self.last_generated_time >= CSRF_REFRESH_AFTER:
            self.generate_token()
        return self._x_token

    def get_user_id(self):
        try:
            response = self.session.get(
                "https://users.roblox.com/v1/users/authenticated",
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as error:
            raise RuntimeError(f"could not verify cookie: {error}") from error

        if response.status_code != 200:
            raise RuntimeError(f"cookie is invalid (HTTP {response.status_code})")

        user_id = response.json().get("id")
        if not user_id:
            raise RuntimeError("cookie is invalid (no user id)")
        self.user_id = user_id
        return user_id

    def request(self, method, url, retries=3, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)

        for attempt in range(retries):
            token = self.x_token()
            if token:
                headers["X-CSRF-TOKEN"] = token

            try:
                response = self.session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=timeout,
                    **kwargs,
                )
            except requests.RequestException as error:
                print(f"[cookie] request failed (attempt {attempt + 1}/{retries}): {error}")
                if attempt >= retries - 1:
                    return None
                time.sleep(_backoff_seconds(attempt, 10))
                continue

            if _is_csrf_rejection(response):
                if attempt < retries - 1:
                    print("[cookie] CSRF token rejected; refreshing and retrying...")
                    self.generate_token()
                    continue
                return response

            if response.status_code == 429 and attempt < retries - 1:
                wait = _backoff_seconds(attempt, 30)
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait = max(wait, min(float(retry_after), 60.0))
                    except (TypeError, ValueError):
                        pass
                print(f"[cookie] rate limited; retrying in {wait}s")
                time.sleep(wait)
                continue

            return response

        return None
