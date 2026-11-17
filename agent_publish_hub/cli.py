"""CLI for agent-publish-hub.

Usage: python3 -m agent_publish_hub --root hub-data <command> ...

Commands: plan, fill, skip, publish, metrics, review, weekly, status,
check, demo. Run `<command> --help` for flags. Exits 0 on success,
1 when `check` fails, 2 on bad input or a refused action.
"""

import argparse
import json
import sys

from . import hub, platforms, store


def _parse_caption(spec):
    if "=" not in spec:
        raise hub.HubError(
            "caption must look like platform=text, got %r" % spec)
    name, text = spec.split("=", 1)
    if not platforms.is_supported(name):
        raise hub.HubError("unsupported platform %r" % name)
    return name, text


def _load(args):
    return store.load(args.root)


def _save(args, state, kind, detail):
    hub.save_with_event(args.root, state, kind, detail)


def _print(data, as_json):
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2,
                         sort_keys=True))


def cmd_plan(args):
    state = _load(args)
    captions = {}
    for spec in args.caption or []:
        name, text = _parse_caption(spec)
        captions[name] = text
    episode = hub.plan(state, args.id, args.title, args.video,
                       args.platforms, captions=captions,
                       scheduled=args.scheduled)
    _save(args, state, "plan", {"episode": args.id,
                                "platforms": args.platforms})
    print("planned %s: %s (%s)"
          % (episode["id"], episode["title"], ", ".join(args.platforms)))
    return 0


def cmd_fill(args):
    state = _load(args)
    hub.fill(state, args.id, args.platform)
    _save(args, state, "fill", {"episode": args.id,
                                "platform": args.platform})
    print("filled %s/%s — ready; publish it or wait for the human click"
          % (args.id, args.platform))
    return 0


def cmd_skip(args):
    state = _load(args)
    hub.skip(state, args.id, args.platform, reason=args.reason or "")
    _save(args, state, "skip", {"episode": args.id,
                                "platform": args.platform,
                                "reason": args.reason or ""})
    print("skipped %s/%s" % (args.id, args.platform))
    return 0


def cmd_publish(args):
    state = _load(args)
    hub.publish(state, args.id, args.platform, args.url,
                confirm=args.confirm, published_at=args.date)
    _save(args, state, "publish", {"episode": args.id,
                                   "platform": args.platform,
                                   "url": args.url})
    print("published %s/%s -> %s" % (args.id, args.platform, args.url))
    return 0


def cmd_metrics(args):
    state = _load(args)
    hub.add_metrics(state, args.id, args.platform, args.date,
                    args.views, args.likes, args.comments, args.shares,
                    args.followers)
    _save(args, state, "metrics", {"episode": args.id,
                                   "platform": args.platform,
                                   "date": args.date,
                                   "views": args.views})
    print("metrics recorded: %s/%s %s views=%d"
          % (args.id, args.platform, args.date, args.views))
    return 0


def _render_review(card):
    lines = ["Review: %s — %s (day %d)"
             % (card["episode"], card["title"], card["day"])]
    for row in card["rows"]:
        name = row["platform"]
        if row.get("note"):
            lines.append("  %-10s %s — %s"
                         % (name, row["status"], row["note"]))
            continue
        line = ("  %-10s views=%d engagement=%.2f%%"
                % (name, row["views"], row["engagement_rate"]))
        if "follower_delta" in row:
            line += " followers=%d (%+d)" % (row["followers"],
                                             row["follower_delta"])
        if "views_vs_prev_pct" in row:
            line += (" | vs %s at day %d: %+0.1f%% (%d views)"
                     % (row["prev_episode"], card["day"],
                        row["views_vs_prev_pct"], row["prev_views"]))
        lines.append(line)
    return "\n".join(lines)


def cmd_review(args):
    state = _load(args)
    card = hub.review(state, args.id, args.day)
    if args.json:
        _print(card, True)
    else:
        print(_render_review(card))
    return 0


def _render_weekly(report):
    lines = ["Weekly %s .. %s: %d publish(es), %d total views"
             % (report["start"], report["end"], report["published"],
                report["total_views"])]
    for name, views in report["per_platform"].items():
        lines.append("  %-10s %d views" % (name, views))
    if report["best_episode"]:
        lines.append("  best episode: %s (%d views)"
                     % (report["best_episode"]["id"],
                        report["best_episode"]["views"]))
    if report["best_platform"]:
        lines.append("  best platform: %s (%d views)"
                     % (report["best_platform"]["platform"],
                        report["best_platform"]["views"]))
    return "\n".join(lines)


def cmd_weekly(args):
    state = _load(args)
    report = hub.weekly(state, as_of=args.as_of)
    if args.json:
        _print(report, True)
    else:
        print(_render_weekly(report))
    return 0


def cmd_status(args):
    state = _load(args)
    if args.id:
        episode = state["episodes"].get(args.id)
        if episode is None:
            raise hub.HubError("no such episode: %s" % args.id)
        episodes = [episode]
    else:
        episodes = sorted(state["episodes"].values(),
                          key=lambda e: e["id"])
    if args.json:
        _print({"episodes": episodes}, True)
        return 0
    if not episodes:
        print("no episodes yet — run `plan` first, or `demo` to seed one")
        return 0
    for episode in episodes:
        parts = []
        for name, entry in sorted(episode["platforms"].items()):
            text = "%s:%s" % (name, entry["status"])
            if entry["status"] == "published":
                text += " %s" % entry["url"]
            parts.append(text)
        print("%s  %s  [%s]" % (episode["id"], episode["title"],
                                " | ".join(parts)))
    return 0


def cmd_check(args):
    state = _load(args)
    failures = hub.check(state)
    if failures:
        for failure in failures:
            print("FAIL: %s" % failure)
        return 1
    print("PASS: %d episode(s), no duplicate uploads, URLs present, "
          "captions within limits" % len(state["episodes"]))
    return 0


def cmd_demo(args):
    state = _load(args)
    seeded = hub.demo(state)
    if seeded:
        _save(args, state, "demo", {"episodes": seeded})
        print("seeded demo episodes: %s" % ", ".join(seeded))
    else:
        print("demo episodes already present — nothing seeded")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="agent-publish-hub",
        description="One episode, many platforms: plan, publish, measure, review.")
    parser.add_argument("--root", default="hub-data",
                        help="hub directory (default: hub-data)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="register an episode across platforms")
    p.add_argument("id", help="episode id, e.g. EP-2026-11-17-01")
    p.add_argument("--title", required=True)
    p.add_argument("--video", required=True,
                   help="video file path or name (its hash is the dedupe key)")
    p.add_argument("--platforms", nargs="+", required=True,
                   choices=platforms.supported_names())
    p.add_argument("--caption", action="append", default=[],
                   help="platform=text (repeatable)")
    p.add_argument("--scheduled", help="planned date YYYY-MM-DD")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("fill", help="mark a platform's upload page filled")
    p.add_argument("id")
    p.add_argument("platform", choices=platforms.supported_names())
    p.set_defaults(func=cmd_fill)

    p = sub.add_parser("skip", help="skip a platform for an episode")
    p.add_argument("id")
    p.add_argument("platform", choices=platforms.supported_names())
    p.add_argument("--reason", default="")
    p.set_defaults(func=cmd_skip)

    p = sub.add_parser("publish", help="record a live URL (dedupe-guarded)")
    p.add_argument("id")
    p.add_argument("platform", choices=platforms.supported_names())
    p.add_argument("--url", required=True)
    p.add_argument("--confirm", action="store_true",
                   help="required on manual platforms: the human clicked publish")
    p.add_argument("--date", help="publish date YYYY-MM-DD (default today)")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("metrics", help="record one day's numbers")
    p.add_argument("id")
    p.add_argument("platform", choices=platforms.supported_names())
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--views", type=int, default=0)
    p.add_argument("--likes", type=int, default=0)
    p.add_argument("--comments", type=int, default=0)
    p.add_argument("--shares", type=int, default=0)
    p.add_argument("--followers", type=int, default=0)
    p.set_defaults(func=cmd_metrics)

    p = sub.add_parser("review", help="day-N review card for an episode")
    p.add_argument("id")
    p.add_argument("--day", type=int, default=1, choices=list(hub.REVIEW_DAYS))
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("weekly", help="last-7-days roll-up")
    p.add_argument("--as-of", help="end date YYYY-MM-DD (default today)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_weekly)

    p = sub.add_parser("status", help="show episodes and platform states")
    p.add_argument("id", nargs="?")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("check", help="CI gate: dedupe, URLs, caption limits")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("demo", help="seed 3 deterministic demo episodes")
    p.set_defaults(func=cmd_demo)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except hub.HubError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
