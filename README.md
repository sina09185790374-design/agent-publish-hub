# agent-publish-hub

One episode, many platforms: plan, publish, measure, review — stdlib only, no network, no keys. English + Persian.

**Pattern** (original code; pattern only, learned from today's radar): CzzzzzzJ/mdldm-maitian runs one creator's whole publish pipeline as a hub — one finished episode goes into a plan, each platform's upload page gets filled in batches, risky platforms stop at fill and wait for the human's final click, a dedupe guard makes sure the same video is never uploaded twice to one platform, links come back, and day-1/3/7 review cards compare each episode with the previous one at the same age. This tool is that idea as a small local CLI for the platforms we actually publish to: `plan` an episode across platforms, `fill`/`publish` with the dedupe guard and the manual-platform confirm, `metrics` samples, `review` day-1/3/7 cards with same-age comparison, `weekly` roll-up, and a `check` CI gate. It is the operations half of the Instagram/Telegram/YouTube routine — the part that remembers what went where, so nothing gets published twice and every episode gets its review.

## How it works

1. **Plan.** One finished video becomes one episode across platforms, each with its own caption. Caption limits are enforced per platform (Instagram 2200, Telegram 4096, YouTube 5000, X 280, TikTok 2200, Threads 500).
2. **Fill, then publish.** `fill` marks a platform's upload page as filled and ready. On **manual** platforms (TikTok, Threads) automation stops here — a human clicks publish, then re-runs `publish` with `--confirm`. On auto platforms `publish` records the live URL directly.
3. **Dedupe guard.** A video is identified by its SHA-256 hash (file bytes when the file exists, otherwise its name). Publishing the same video twice to one platform is refused — the mistake maitian's guard exists to prevent.
4. **Metrics.** One sample per platform per day: views, likes, comments, shares, followers. A repeated date replaces the old sample.
5. **Review.** `review --day 1|3|7` builds the card per platform: views at that age, engagement rate, follower delta since publish day, and the same-age comparison with the previous episode on that platform (`+19.5%` vs EP-… at day 7). Platforms are compared at the same age even when they were published on different days.
6. **Weekly.** Last-7-days roll-up: publish count, total views, per-platform totals, best episode, best platform.
7. **Check.** CI gate: no duplicate uploads, every published entry carries a URL and a date, captions inside limits, metrics non-negative. Exit 0 = PASS, 1 = FAIL.

State lives in `--root` (default `hub-data/`): `hub.json` (the whole state) plus `events.jsonl` (append-only log of every change).

## Usage

```bash
python3 -m agent_publish_hub --root hub-data demo
python3 -m agent_publish_hub --root hub-data review EP-2026-11-12-01 --day 7
python3 -m agent_publish_hub --root hub-data weekly --as-of 2026-11-17
python3 -m agent_publish_hub --root hub-data check

python3 -m agent_publish_hub --root hub-data plan EP-2026-11-17-01 \
  --title "The fox returns" --video reel-ep18.mp4 \
  --platforms instagram telegram youtube \
  --caption instagram="Hook first, facts second. #gaming"

python3 -m agent_publish_hub --root hub-data fill EP-2026-11-17-01 instagram
python3 -m agent_publish_hub --root hub-data publish EP-2026-11-17-01 instagram \
  --url https://instagram.com/reel/XXXX --date 2026-11-17

# Manual platform: fill it, click publish yourself, then confirm:
python3 -m agent_publish_hub --root hub-data publish EP-2026-11-17-01 tiktok \
  --url https://tiktok.com/@x/video/YYYY --confirm --date 2026-11-17

python3 -m agent_publish_hub --root hub-data metrics EP-2026-11-17-01 instagram \
  --date 2026-11-18 --views 1450 --likes 150 --comments 12 --shares 20 --followers 12560
python3 -m agent_publish_hub --root hub-data review EP-2026-11-17-01 --day 1
python3 -m agent_publish_hub --root hub-data status
```

`--json` on `review`, `weekly` and `status` prints machine-readable output. Exit codes: 0 success, 1 `check` failed, 2 bad input or a refused action (dedupe guard, manual platform without `--confirm`, metrics before publish).

## Example

Demo hub, day-7 review of the third episode (verified run: `examples/demo-run.md`):

> Review: EP-2026-11-12-01 — The owl counts the stars (day 7)
>   instagram  views=4900 engagement=14.49% followers=10980 (+620) | vs EP-2026-11-11-01 at day 7: +19.5% (4100 views)
>   telegram   views=700 engagement=14.43% followers=10140 (+70) | vs EP-2026-11-11-01 at day 7: +14.8% (610 views)
>   youtube    views=2800 engagement=14.50% followers=10560 (+360) | vs EP-2026-11-11-01 at day 7: +16.7% (2400 views)

And the guard doing its job — planning the same video again and trying to publish it to Instagram:

> error: dedupe guard: this video is already published on instagram as EP-2026-11-12-01 (https://example.invalid/instagram/EP-2026-11-12-01)

## Tests

```bash
python3 -m unittest discover -s tests
# 42 tests, all passing. The suite caught 1 real bug before shipping —
# the test helper reused one video name across two episodes and the
# dedupe guard (correctly) refused the second publish.
```

## فارسی

یک قسمت، چند پلتفرم: برنامه‌ریزی، انتشار، اندازه‌گیری، مرور — فقط استاندارد پایتون، بدون شبکه و بدون کلید.

الگو (کد اصلی؛ فقط الگو، برگرفته از رادار امروز): ‏CzzzzzzJ/mdldm-maitian‏ کل خط انتشار یک سازنده را به‌صورت یک هاب اجرا می‌کند — یک قسمت تمام‌شده وارد برنامه می‌شود، صفحه آپلود هر پلتفرم پر می‌شود، پلتفرم‌های پرریسک در مرحله پرکردن می‌ایستند و منتظر کلیک نهایی انسان می‌مانند، نگهبان تکراری نمی‌گذارد یک ویدیو دوبار در یک پلتفرم آپلود شود، لینک‌ها برمی‌گردند، و کارت‌های مرور روز ۱/۳/۷ هر قسمت را با قسمت قبلی در همان سن مقایسه می‌کنند. این ابزار همان ایده است در یک CLI کوچک محلی برای پلتفرم‌هایی که ما واقعاً در آن‌ها منتشر می‌کنیم: ‏`plan`‏ برای برنامه‌ریزی یک قسمت در چند پلتفرم، ‏`fill`/`publish`‏ با نگهبان تکراری و تأیید دستی، ‏`metrics`‏ برای نمونه‌های روزانه، ‏`review`‏ برای کارت روز ۱/۳/۷ با مقایسه هم‌سن، ‏`weekly`‏ برای جمع‌بندی هفته، و ‏`check`‏ به‌عنوان گیت CI. این نیمه عملیاتی روتین اینستاگرام/تلگرام/یوتیوب است — بخشی که یادش می‌ماند چه چیزی کجا رفت، تا چیزی دوبار منتشر نشود و هر قسمت مرورش را بگیرد.

دستورها همان بخش انگلیسی بالا هستند؛ ‏`demo`‏ سه قسمت نمایشی قطعی می‌سازد و ‏`check`‏ با خروج ۰ یعنی قبول و ۱ یعنی رد.
