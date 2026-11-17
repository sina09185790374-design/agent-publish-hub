"""Platform table for agent-publish-hub.

Each platform knows its caption limit and whether the final publish click
may be automated ("auto") or must be done by a human ("manual"). The
manual set mirrors the maitian pattern: risky platforms get filled and
stopped, and a human clicks the final publish — automation never takes the
last step where a platform punishes it.
"""

PLATFORMS = {
    "instagram": {"caption_limit": 2200, "mode": "auto",
                  "label": "Instagram"},
    "telegram": {"caption_limit": 4096, "mode": "auto",
                 "label": "Telegram"},
    "youtube": {"caption_limit": 5000, "mode": "auto",
                "label": "YouTube"},
    "x": {"caption_limit": 280, "mode": "auto",
          "label": "X"},
    "tiktok": {"caption_limit": 2200, "mode": "manual",
               "label": "TikTok"},
    "threads": {"caption_limit": 500, "mode": "manual",
                "label": "Threads"},
}


def is_supported(name):
    return name in PLATFORMS


def caption_limit(name):
    return PLATFORMS[name]["caption_limit"]


def mode(name):
    return PLATFORMS[name]["mode"]


def supported_names():
    return sorted(PLATFORMS)
