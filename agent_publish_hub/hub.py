"""Core logic for agent-publish-hub: one episode, many platforms.

The pipeline mirrors the maitian pattern, shrunk to a local stdlib CLI:

    plan -> fill -> publish -> metrics -> review (day 1/3/7) -> weekly

* ``plan`` registers an episode (one finished video) across platforms,
  each with its own caption.
* ``fill`` marks a platform's upload page as filled and ready. On manual
  platforms this is where automation STOPS — a human clicks publish.
* ``publish`` records the live URL. It refuses to publish the same video
  twice to one platform (dedupe guard, keyed on the video hash) and refuses
  a manual platform without ``--confirm`` (the human's click).
* ``metrics`` records one sample per platform per day (views, likes,
  comments, shares, followers).
* ``review`` builds the day-N card: per-platform views, engagement rate,
  same-age comparison with the previous episode, follower delta.
* ``weekly`` rolls the last 7 days up: totals, best episode, best platform.
* ``check`` is the CI gate: no duplicate uploads, every published entry
  carries a URL, captions inside per-platform limits.
"""

import hashlib
import os
from datetime import date, timedelta

from . import platforms, store

REVIEW_DAYS = (1, 3, 7)


class HubError(Exception):
    """A user-facing error: bad input or a refused action."""


def today_iso():
    return date.today().isoformat()


def parse_date(text, what="date"):
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise HubError("invalid %s %r (want YYYY-MM-DD)" % (what, text))


def video_hash(video):
    """Stable identity for a video: file bytes when the file exists,
    otherwise the name itself. Two episodes with the same hash are the
    same video, and the dedupe guard treats them as one."""
    if video and os.path.isfile(video):
        digest = hashlib.sha256()
        with open(video, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
        return "file:" + digest.hexdigest()
    return "name:" + hashlib.sha256(video.encode("utf-8")).hexdigest()


def _episode(state, episode_id):
    try:
        return state["episodes"][episode_id]
    except KeyError:
        raise HubError("no such episode: %s" % episode_id)


def _platform_entry(episode, platform):
    try:
        return episode["platforms"][platform]
    except KeyError:
        raise HubError("episode %s has no platform %s"
                       % (episode["id"], platform))


def plan(state, episode_id, title, video, platform_names,
         captions=None, scheduled=None, created=None):
    if not episode_id or any(c in episode_id for c in " /\\"):
        raise HubError("episode id must be one token, e.g. EP-2026-11-17-01")
    if episode_id in state["episodes"]:
        raise HubError("episode already exists: %s" % episode_id)
    if not platform_names:
        raise HubError("plan at least one platform: %s"
                       % ", ".join(platforms.supported_names()))
    for name in platform_names:
        if not platforms.is_supported(name):
            raise HubError("unsupported platform %r (supported: %s)"
                           % (name, ", ".join(platforms.supported_names())))
    if len(set(platform_names)) != len(platform_names):
        raise HubError("duplicate platform in plan: %s"
                       % ", ".join(platform_names))
    captions = captions or {}
    for name, caption in captions.items():
        if name not in platform_names:
            raise HubError("caption for unplanned platform %r" % name)
        limit = platforms.caption_limit(name)
        if len(caption) > limit:
            raise HubError(
                "caption for %s is %d chars, over the %d limit"
                % (name, len(caption), limit))
    if scheduled:
        parse_date(scheduled, "scheduled date")
    episode = {
        "id": episode_id,
        "title": title,
        "video": video,
        "video_hash": video_hash(video),
        "created": created or today_iso(),
        "scheduled": scheduled or "",
        "platforms": {
            name: {
                "status": "planned",
                "caption": captions.get(name, ""),
                "url": "",
                "published_at": "",
                "metrics": [],
            }
            for name in platform_names
        },
    }
    state["episodes"][episode_id] = episode
    return episode


def fill(state, episode_id, platform):
    episode = _episode(state, episode_id)
    entry = _platform_entry(episode, platform)
    if entry["status"] == "published":
        raise HubError("%s/%s is already published" % (episode_id, platform))
    if entry["status"] == "skipped":
        raise HubError("%s/%s was skipped; re-plan it to revive"
                       % (episode_id, platform))
    entry["status"] = "filled"
    return entry


def skip(state, episode_id, platform, reason=""):
    episode = _episode(state, episode_id)
    entry = _platform_entry(episode, platform)
    if entry["status"] == "published":
        raise HubError("%s/%s is already published; cannot skip"
                       % (episode_id, platform))
    entry["status"] = "skipped"
    entry["skip_reason"] = reason
    return entry


def publish(state, episode_id, platform, url, confirm=False,
            published_at=None):
    episode = _episode(state, episode_id)
    entry = _platform_entry(episode, platform)
    if entry["status"] == "published":
        raise HubError("%s/%s is already published at %s"
                       % (episode_id, platform, entry["url"]))
    if entry["status"] == "skipped":
        raise HubError("%s/%s was skipped; re-plan it to publish"
                       % (episode_id, platform))
    if platforms.mode(platform) == "manual" and not confirm:
        raise HubError(
            "%s is a manual platform: fill it, click publish yourself, "
            "then re-run with --confirm" % platform)
    if not url:
        raise HubError("publish needs the live --url")
    # Dedupe guard: the same video must never go live twice on one platform.
    for other_id, other in state["episodes"].items():
        if other_id == episode_id:
            continue
        if other["video_hash"] != episode["video_hash"]:
            continue
        other_entry = other["platforms"].get(platform)
        if other_entry and other_entry["status"] == "published":
            raise HubError(
                "dedupe guard: this video is already published on %s "
                "as %s (%s)" % (platform, other_id, other_entry["url"]))
    published = published_at or today_iso()
    parse_date(published, "published date")
    entry["status"] = "published"
    entry["url"] = url
    entry["published_at"] = published
    return entry


def add_metrics(state, episode_id, platform, sample_date,
                views, likes, comments, shares, followers):
    episode = _episode(state, episode_id)
    entry = _platform_entry(episode, platform)
    if entry["status"] != "published":
        raise HubError("metrics need a published %s/%s (status: %s)"
                       % (episode_id, platform, entry["status"]))
    day = parse_date(sample_date, "metrics date")
    if day < parse_date(entry["published_at"], "published date"):
        raise HubError("metrics date %s is before the publish date %s"
                       % (sample_date, entry["published_at"]))
    for name, value in (("views", views), ("likes", likes),
                        ("comments", comments), ("shares", shares),
                        ("followers", followers)):
        if value < 0:
            raise HubError("metrics %s cannot be negative: %d" % (name, value))
    sample = {"date": sample_date, "views": views, "likes": likes,
              "comments": comments, "shares": shares,
              "followers": followers}
    metrics = entry["metrics"]
    for i, old in enumerate(metrics):
        if old["date"] == sample_date:
            metrics[i] = sample
            break
    else:
        metrics.append(sample)
    metrics.sort(key=lambda s: s["date"])
    return sample


def _sample_at_or_before(metrics, when):
    """Latest sample on or before `when` (a date), or None."""
    best = None
    for sample in metrics:
        if parse_date(sample["date"], "sample date") <= when:
            best = sample
    return best


def _previous_episode(state, episode, platform):
    """Most recently published earlier episode on the same platform."""
    published = episode["platforms"][platform]["published_at"]
    best = None
    for other in state["episodes"].values():
        if other["id"] == episode["id"]:
            continue
        entry = other["platforms"].get(platform)
        if not entry or entry["status"] != "published":
            continue
        if entry["published_at"] < published:
            if best is None or entry["published_at"] > best[1]:
                best = (other, entry["published_at"])
    return best[0] if best else None


def engagement_rate(sample):
    views = sample["views"]
    if views <= 0:
        return None
    acted = sample["likes"] + sample["comments"] + sample["shares"]
    return round(100.0 * acted / views, 2)


def review(state, episode_id, day):
    """Day-N review card for one episode.

    Per platform, the as-of date is published_at + N days, so platforms
    published on different days are each compared at the same age. The
    same-age comparison uses the previous episode on that platform at
    the same day-age.
    """
    if day < 0:
        raise HubError("review day cannot be negative: %d" % day)
    episode = _episode(state, episode_id)
    rows = []
    for name, entry in sorted(episode["platforms"].items()):
        if entry["status"] != "published":
            rows.append({"platform": name, "status": entry["status"],
                         "note": "not published yet"})
            continue
        published = parse_date(entry["published_at"], "published date")
        as_of = published + timedelta(days=day)
        sample = _sample_at_or_before(entry["metrics"], as_of)
        if sample is None:
            rows.append({"platform": name, "status": "published",
                         "published_at": entry["published_at"],
                         "as_of": as_of.isoformat(),
                         "note": "no metrics yet"})
            continue
        row = {"platform": name, "status": "published",
               "published_at": entry["published_at"],
               "as_of": as_of.isoformat(),
               "views": sample["views"],
               "likes": sample["likes"], "comments": sample["comments"],
               "shares": sample["shares"],
               "engagement_rate": engagement_rate(sample)}
        first = _sample_at_or_before(
            entry["metrics"], published)
        if first is not None:
            row["followers"] = sample["followers"]
            row["follower_delta"] = sample["followers"] - first["followers"]
        prev = _previous_episode(state, episode, name)
        if prev is not None:
            prev_entry = prev["platforms"][name]
            prev_published = parse_date(prev_entry["published_at"],
                                        "published date")
            prev_sample = _sample_at_or_before(
                prev_entry["metrics"], prev_published + timedelta(days=day))
            if prev_sample is not None and prev_sample["views"] > 0:
                row["prev_episode"] = prev["id"]
                row["prev_views"] = prev_sample["views"]
                row["views_vs_prev_pct"] = round(
                    100.0 * (sample["views"] - prev_sample["views"])
                    / prev_sample["views"], 1)
        rows.append(row)
    return {"episode": episode_id, "title": episode["title"],
            "day": day, "rows": rows}


def weekly(state, as_of=None):
    """Last-7-days roll-up ending on `as_of` (default today)."""
    end = parse_date(as_of, "as-of date") if as_of else date.today()
    start = end - timedelta(days=6)
    per_platform = {}
    per_episode = {}
    published_count = 0
    for episode in state["episodes"].values():
        ep_total = 0
        ep_published = False
        for name, entry in episode["platforms"].items():
            if entry["status"] != "published":
                continue
            published = parse_date(entry["published_at"], "published date")
            if not (start <= published <= end):
                continue
            ep_published = True
            published_count += 1
            sample = _sample_at_or_before(entry["metrics"], end)
            views = sample["views"] if sample else 0
            per_platform[name] = per_platform.get(name, 0) + views
            ep_total += views
        if ep_published:
            per_episode[episode["id"]] = {
                "title": episode["title"], "views": ep_total}
    best_episode = None
    if per_episode:
        best_episode = max(per_episode.items(), key=lambda kv: kv[1]["views"])
    best_platform = None
    if per_platform:
        best_platform = max(per_platform.items(), key=lambda kv: kv[1])
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "published": published_count,
        "total_views": sum(per_platform.values()),
        "per_platform": dict(sorted(per_platform.items())),
        "per_episode": dict(sorted(per_episode.items())),
        "best_episode": ({"id": best_episode[0], **best_episode[1]}
                         if best_episode else None),
        "best_platform": ({"platform": best_platform[0],
                           "views": best_platform[1]}
                          if best_platform else None),
    }


def check(state):
    """CI gate. Returns a list of failure strings (empty = PASS)."""
    failures = []
    seen_published = {}
    for episode in state["episodes"].values():
        for name, entry in episode["platforms"].items():
            where = "%s/%s" % (episode["id"], name)
            if entry["status"] == "published":
                if not entry.get("url"):
                    failures.append("%s: published without a URL" % where)
                if not entry.get("published_at"):
                    failures.append("%s: published without a date" % where)
                key = (episode["video_hash"], name)
                if key in seen_published:
                    failures.append(
                        "%s: duplicate upload — same video already "
                        "published on %s as %s"
                        % (where, name, seen_published[key]))
                else:
                    seen_published[key] = episode["id"]
            caption = entry.get("caption", "")
            if name in platforms.PLATFORMS:
                limit = platforms.caption_limit(name)
                if len(caption) > limit:
                    failures.append(
                        "%s: caption %d chars over the %d limit"
                        % (where, len(caption), limit))
            for sample in entry.get("metrics", []):
                for field in ("views", "likes", "comments", "shares",
                              "followers"):
                    if sample.get(field, 0) < 0:
                        failures.append(
                            "%s: negative %s in metrics %s"
                            % (where, field, sample.get("date", "?")))
    return failures


def demo(state):
    """Seed a deterministic demo hub: 3 episodes, 3 platforms, metrics
    on days 0/1/3/7. Re-running demo on a hub that already has these
    episodes is a no-op for the existing ones."""
    demo_data = [
        ("EP-2026-11-10-01", "The fox returns to the forest",
         "whisperwood-ep15.mp4", ["instagram", "telegram", "youtube"],
         "2026-11-10",
         {"instagram": [1200, 1450, 2100, 3400],
          "telegram": [300, 340, 410, 520],
          "youtube": [800, 950, 1300, 2100]}),
        ("EP-2026-11-11-01", "The otter remembers the river",
         "whisperwood-ep16.mp4", ["instagram", "telegram", "youtube"],
         "2026-11-11",
         {"instagram": [1500, 1800, 2600, 4100],
          "telegram": [320, 380, 470, 610],
          "youtube": [900, 1100, 1500, 2400]}),
        ("EP-2026-11-12-01", "The owl counts the stars",
         "whisperwood-ep17.mp4", ["instagram", "telegram", "youtube"],
         "2026-11-12",
         {"instagram": [1800, 2200, 3100, 4900],
          "telegram": [350, 410, 520, 700],
          "youtube": [1000, 1250, 1700, 2800]}),
    ]
    seeded = []
    for ep_id, title, video, plats, published, views in demo_data:
        if ep_id in state["episodes"]:
            continue
        plan(state, ep_id, title, video, plats, created=published)
        for name in plats:
            publish(state, ep_id, name,
                    "https://example.invalid/%s/%s" % (name, ep_id),
                    confirm=True, published_at=published)
            base = parse_date(published, "published date")
            for offset, view_count in zip((0, 1, 3, 7), views[name]):
                when = base + timedelta(days=offset)
                add_metrics(state, ep_id, name, when.isoformat(),
                            view_count,
                            likes=view_count // 10,
                            comments=view_count // 50,
                            shares=view_count // 40,
                            followers=10000 + view_count // 5)
        seeded.append(ep_id)
    return seeded


def save_with_event(root, state, kind, detail):
    store.save(root, state)
    store.log_event(root, {"kind": kind, "detail": detail})
