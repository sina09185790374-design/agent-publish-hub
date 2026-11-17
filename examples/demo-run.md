# Verified demo run (2026-11-17)

Commands run against a fresh hub (`--root /tmp/hub-demo`); output copied
verbatim from the terminal.

```bash
$ python3 -m agent_publish_hub --root /tmp/hub-demo demo
seeded demo episodes: EP-2026-11-10-01, EP-2026-11-11-01, EP-2026-11-12-01

$ python3 -m agent_publish_hub --root /tmp/hub-demo review EP-2026-11-12-01 --day 7
Review: EP-2026-11-12-01 — The owl counts the stars (day 7)
  instagram  views=4900 engagement=14.49% followers=10980 (+620) | vs EP-2026-11-11-01 at day 7: +19.5% (4100 views)
  telegram   views=700 engagement=14.43% followers=10140 (+70) | vs EP-2026-11-11-01 at day 7: +14.8% (610 views)
  youtube    views=2800 engagement=14.50% followers=10560 (+360) | vs EP-2026-11-11-01 at day 7: +16.7% (2400 views)

$ python3 -m agent_publish_hub --root /tmp/hub-demo weekly --as-of 2026-11-17
Weekly 2026-11-11 .. 2026-11-17: 6 publish(es), 9890 total views
  instagram  5700 views
  telegram   990 views
  youtube    3200 views
  best episode: EP-2026-11-12-01 (5320 views)
  best platform: instagram (5700 views)

$ python3 -m agent_publish_hub --root /tmp/hub-demo status
EP-2026-11-10-01  The fox returns to the forest  [instagram:published https://example.invalid/instagram/EP-2026-11-10-01 | telegram:published https://example.invalid/telegram/EP-2026-11-10-01 | youtube:published https://example.invalid/youtube/EP-2026-11-10-01]
EP-2026-11-11-01  The otter remembers the river  [instagram:published https://example.invalid/instagram/EP-2026-11-11-01 | telegram:published https://example.invalid/telegram/EP-2026-11-11-01 | youtube:published https://example.invalid/youtube/EP-2026-11-11-01]
EP-2026-11-12-01  The owl counts the stars  [instagram:published https://example.invalid/instagram/EP-2026-11-12-01 | telegram:published https://example.invalid/telegram/EP-2026-11-12-01 | youtube:published https://example.invalid/youtube/EP-2026-11-12-01]

$ python3 -m agent_publish_hub --root /tmp/hub-demo check
PASS: 3 episode(s), no duplicate uploads, URLs present, captions within limits

$ python3 -m agent_publish_hub --root /tmp/hub-demo plan EP-2026-11-12-02 --title "Same video, second try" --video whisperwood-ep17.mp4 --platforms instagram
planned EP-2026-11-12-02: Same video, second try (instagram)

$ python3 -m agent_publish_hub --root /tmp/hub-demo publish EP-2026-11-12-02 instagram --url https://example.invalid/ig-dupe --date 2026-11-13
error: dedupe guard: this video is already published on instagram as EP-2026-11-12-01 (https://example.invalid/instagram/EP-2026-11-12-01)
# exit code 2 — the guard refused the duplicate upload.
```

Tests: `python3 -m unittest discover -s tests` → 42 tests, OK.
