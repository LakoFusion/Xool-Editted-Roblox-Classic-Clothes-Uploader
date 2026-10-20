<div align="center">

# Xool — Roblox Classic Clothes Uploader

**Tự động hóa quét catalog, tối ưu texture bằng AI, lọc NSFW và xuất bản Classic Shirts & Pants lên Roblox Group — kèm Terminal Console UI thời gian thực.**

![Version](https://img.shields.io/badge/version-1.0-00bcd4?style=for-the-badge)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](https://opensource.org/licenses/MIT)

[Tính năng](#mục-đích--tính-năng-cốt-lõi) · [Giao diện](#giao-diện-terminal-preview) · [Cài đặt](#cài-đặt--hướng-dẫn-sử-dụng-quick-start) · [Cấu trúc](#cấu-trúc-thư-mục--workflow) · [FAQ](#xử-lý-lỗi-thường-gặp-troubleshooting--faq) · [Hỗ trợ](#kết-nối--hỗ-trợ-connect--support)

</div>

---

## Giao diện Terminal Preview

Console UI thuần ANSI (không dùng thư viện TUI ngoài) chạy trên thread nền riêng, tự làm mới số liệu mà không chặn luồng upload:

```text
Clothes Uploader Roblox  v1.0
Status     : Running
Uptime     : 00:04:12

Account    : group 12345678 | 1 cookie
Target     : y2k emo goth grunge
Mode       : gemini_cookie | enhance on

Uploaded   : 1
Remaining  : 0
Skipped    : 3
Failed     : 0
Pending    : 0
Round      : 2
Candidates : 18

Recent activity
[10:54:12] > scan classicshirts: 18 candidate(s)
[10:54:15] > downloaded one asset
[10:54:20] > enhanced asset style=y2k mode=provider
[10:54:28] > asset 189283741 moderation status: ReviewApproved
[10:54:32] > published one asset
[Ctrl+C to stop]
```

---

## Mục đích & Tính năng cốt lõi

**Xool** là pipeline khép kín cho các Group kinh doanh Classic Clothing: tìm mẫu, dịch tên, kiểm tra an toàn, nâng cấp texture, upload và mở bán — tất cả trong một vòng lặp tự động.

- **Đa luồng & bất đồng bộ**: UI vẽ trên daemon thread `console-ui` (`src/ui`) với `threading.Lock`/`RLock`; `LogStream` gom log theo dòng nên terminal không giật lag và luồng mạng không bị chặn.
- **Quản lý token & phiên tự động** (`src/cookie`): xác thực `.ROBLOSECURITY`, tự làm mới `X-CSRF-TOKEN` khi gặp 403 CSRF, exponential backoff + tôn trọng `Retry-After` (tối đa 60s) khi bị HTTP 429.
- **Tương thích proxy**: toàn bộ traffic đi qua `requests.Session`, tự đọc `HTTP_PROXY` / `HTTPS_PROXY` từ môi trường; SOCKS cần cài thêm `PySocks` (`pip install requests[socks]`).
- **Quét catalog thông minh** (`src/scrape`): phân trang cursor, tối đa 150 item mỗi lượt quét, xáo trộn pool 40 ứng viên mỗi vòng và loại bỏ creator/từ khóa trong blacklist.
- **Dịch tên & chuẩn hóa SEO** (`src/naming.py`): từ điển offline VI→EN (~90 cụm thời trang), bỏ dấu NFD, loại ký tự non-Latin — tên file và tên hiển thị Roblox luôn là tiếng Anh.
- **Chống trùng lặp** (`src/files`): perceptual hash (`imagehash`) đối chiếu với kho ảnh, tránh tải/upload lại mẫu đã có.
- **Lọc NSFW** (`src/download`): mạng nơ-ron TensorFlow + OpenNSFW2 chặn ảnh nhạy cảm vượt ngưỡng `max_nudity_value`.
- **Enhance Hybrid** (`src/enhance`): Gemini Web Cookie (không tốn quota API), Gemini API xoay vòng key, Stable Diffusion Replicate, hoặc engine procedural cục bộ (căn đường may UV `uv_spec.py`, phủ bóng AO, độ sâu vải).
- **Bảo vệ Robux** (`src/upload`): nhận diện phí cọc 80 Robux/item; nếu publish lỗi tạm thời, sản phẩm vào `src/assets/pending_sales.json` để thử lại định kỳ thay vì mất tiền.
- **Chống treo vô hạn**: tự dừng an toàn sau 10 vòng liên tiếp không có tiến trình hoặc 10 vòng crash liên tiếp.

---

## Disclaimer & Cảnh báo bảo mật

> [!WARNING]
> **Rủi ro khóa tài khoản theo Roblox Terms of Service**
> Công cụ tự động hóa tương tác trực tiếp với API Roblox. Việc sử dụng có thể vi phạm TOS và dẫn tới cảnh cáo, khóa tạm thời hoặc khóa vĩnh viễn tài khoản/Group. **Tác giả không chịu trách nhiệm cho bất kỳ thiệt hại nào** về tài khoản, Group hoặc số dư Robux. Nên chạy bằng tài khoản phụ có quyền hạn giới hạn.

> [!CAUTION]
> **Tuyệt đối không chia sẻ token/cookie/password**
> `.ROBLOSECURITY`, `gemini_cookie` và API key cho phép đăng nhập toàn quyền vào tài khoản. Không gửi `config.json` / `ai_settings.json` cho bất kỳ ai và không commit chúng lên GitHub.

Kiểm tra `.gitignore` trước khi push để không lộ `config.json`, `.env`, `proxies.txt`:

```gitignore
config.json
ai_settings.json
.env
proxies.txt
*.cookie
src/assets/temp/
src/assets/pending_sales.json
__pycache__/
*.py[cod]
.venv/
venv/
```

---

## Cài đặt & Hướng dẫn sử dụng (Quick Start)

**Yêu cầu:** Windows 10/11, Linux hoặc macOS; **Python 3.10 / 3.11 (64-bit)**. Dự án không dùng npm.

```bash
# 1) Tạo và kích hoạt môi trường ảo
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # Linux/macOS

# 2) Cài dependencies
pip install -r requirements.txt

# 3) Khởi chạy
python main.py
```

### Cấu hình `config.json` (bắt buộc)

```json
{
    "groups": {
        "YOUR_GROUP_ID": {
            "uploader_cookies": ["_|WARNING:-DO-NOT-SHARE-THIS...|_YOUR_COOKIE"]
        }
    },
    "upload_amount": 5,
    "assets_price": 5,
    "searching_tags": "y2k emo goth grunge",
    "require_one_tag_in_name": true,
    "sleep_each_upload": 5,
    "max_nudity_value": 0.3,
    "delete_all_images_on_restart": false,
    "blacklisted_words": ["nike", "adidas", "gucci", "supreme", "hot", "bikini"],
    "description": "★ High quality Y2K aesthetic fit crafted for the streets.\n\ntags: y2k, cyber, goth, grunge, streetwear"
}
```

| Khóa | Ý nghĩa |
| --- | --- |
| `groups` | Group ID → danh sách cookie `.ROBLOSECURITY` của uploader |
| `upload_amount` | Số sản phẩm cần upload trong phiên chạy |
| `assets_price` | Giá bán trên Marketplace (tối thiểu 5 Robux) |
| `searching_tags` | Từ khóa quét catalog |
| `sleep_each_upload` | Nghỉ giữa các lần upload (giây) |
| `max_nudity_value` | Ngưỡng NSFW tối đa (khuyến nghị 0.25–0.35) |
| `require_one_tag_in_name` | Bắt buộc tên chứa ít nhất một tag tìm kiếm |
| `delete_all_images_on_restart` | Xóa toàn bộ ảnh cũ khi khởi động |

### Cấu hình `ai_settings.json` (tùy chọn — bật AI Enhance)

```json
{
    "enhance_clothes": true,
    "enhance_provider": "gemini_cookie",
    "gemini_cookie": "YOUR_GEMINI_BROWSER_COOKIE"
}
```

`enhance_provider` nhận: `local` (mặc định), `gemini_cookie`, `gemini` (API key), `replicate_sd`, `openai`, `photoroom`.

---

## Cấu trúc thư mục & Workflow

```text
xool-main/
├── main.py                 # Vòng lặp điều phối: pick → process → upload → publish
├── config.json             # Cấu hình chính (group, cookie, tag, filter, giá)
├── ai_settings.json        # Cấu hình enhance (Gemini / Replicate)
├── requirements.txt        # requests, Pillow, tensorflow, opennsfw2, imagehash...
├── assets/                 # Media (demo.gif)
└── src/
    ├── cookie/             # .ROBLOSECURITY, CSRF refresh, 429 backoff
    ├── download/           # Tải asset gốc + kiểm tra NSFW
    ├── enhance/            # Gemini Web/API, Replicate, UV seam, AO shading
    ├── files/              # ImageHash chống trùng lặp, dọn file
    ├── naming.py           # Dịch tên VI→EN, lọc ký tự non-Latin
    ├── scrape/             # Catalog cursor pagination + blacklist
    ├── ui/                 # Console UI ANSI đa luồng
    └── upload/             # Tạo asset, chờ moderation, publish, pending queue
```

**Luồng chạy — Input → Xử lý → Output:**

```text
[INPUT]   Cookie + Group ID + searching_tags + assets_price (config.json)
   ↓
[XỬ LÝ]   Scrape catalog (150 item) → dịch tên EN → lọc blacklist
          → dedupe ImageHash → NSFW check → enhance (AI/local)
   ↓
[OUTPUT]  Upload asset (phí cọc 80 R$) → chờ moderation → publish lên Group
          → thanh toán thành công: hiển thị trên UI
          → lỗi tạm thời: lưu pending_sales.json, tự thử lại sau
```

---

## Xử lý lỗi thường gặp (Troubleshooting / FAQ)

**1. `ModuleNotFoundError` / `ImportError: DLL load failed` (thiếu thư viện)**
Cài đủ gói bằng `pip install -r requirements.txt`. Trên Windows, TensorFlow cần **Visual C++ Redistributable (x64)** — tải từ Microsoft rồi khởi động lại máy. Dùng Python 3.10/3.11 64-bit.

**2. `InvalidURL: Missing scheme` hoặc `ProxyError` (sai format proxy)**
Proxy phải có scheme và đúng cấu trúc `scheme://user:pass@host:port`:
```powershell
$env:HTTP_PROXY="http://user:pass@ip:port"
$env:HTTPS_PROXY="http://user:pass@ip:port"
# SOCKS: pip install "requests[socks]" rồi dùng socks5://user:pass@ip:port
```

**3. `cookie is invalid (HTTP 401/403)` (token hết hạn)**
Cookie đã hết hạn hoặc bị thu hồi. Đăng nhập lại Roblox trong trình duyệt ẩn danh, F12 → Application → Cookies → copy `.ROBLOSECURITY` mới vào `config.json`. Nếu chỉ lỗi CSRF, tool tự refresh token và thử lại.

**4. `[cookie] rate limited; retrying in XXs` (HTTP 429)**
Tool tự chờ theo `Retry-After` (tối đa 60s). Nếu lặp lại nhiều, tăng `sleep_each_upload` lên 10–15 giây hoặc đổi IP/proxy.

> [!NOTE]
> Lỗi `80 Robux is needed`: Roblox yêu cầu phí cọc publishing cho Classic Clothing. Nạp đủ Robux vào Group hoặc tài khoản uploader trước khi chạy.

---

## Kết nối & Hỗ trợ (Connect & Support)

- **Discord**: [https://discord.gg/rxw8Hwk3qA](https://discord.gg/rxw8Hwk3qA)
- **TikTok**: [@lakofusion](https://www.tiktok.com/@lakofusion)
- **YouTube**: [@lakofusion2010](https://www.youtube.com/@lakofusion2010)

---

## License

MIT License

```text
Copyright (c) 2026 Lako Fusion

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
