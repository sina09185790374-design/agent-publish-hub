"""Tests for agent-publish-hub. Stdlib unittest, no network."""

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent_publish_hub import cli, hub, platforms, store  # noqa: E402


class HubTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="publish-hub-test-")
        self.root = os.path.join(self.tmp, "hub")
        self.state = store.empty_state()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plan(self, ep_id="EP-1", video="clip.mp4",
              plats=("instagram", "telegram"), **kw):
        return hub.plan(self.state, ep_id, "Title " + ep_id, video,
                        list(plats), **kw)

    # --- plan ----------------------------------------------------------

    def test_plan_creates_episode_with_planned_platforms(self):
        ep = self._plan()
        self.assertEqual(ep["title"], "Title EP-1")
        self.assertEqual(ep["platforms"]["instagram"]["status"], "planned")
        self.assertEqual(ep["platforms"]["telegram"]["status"], "planned")
        self.assertEqual(ep["video_hash"],
                         hub.video_hash("clip.mp4"))

    def test_plan_rejects_unknown_platform(self):
        with self.assertRaises(hub.HubError):
            hub.plan(self.state, "EP-1", "t", "v.mp4", ["myspace"])

    def test_plan_rejects_duplicate_episode_id(self):
        self._plan()
        with self.assertRaises(hub.HubError):
            self._plan()

    def test_plan_rejects_duplicate_platform(self):
        with self.assertRaises(hub.HubError):
            self._plan(plats=("instagram", "instagram"))

    def test_plan_rejects_over_limit_caption(self):
        with self.assertRaises(hub.HubError):
            self._plan(captions={"x": "a" * 281})

    def test_plan_accepts_caption_at_limit(self):
        ep = self._plan(plats=("x",), captions={"x": "a" * 280})
        self.assertEqual(len(ep["platforms"]["x"]["caption"]), 280)

    def test_plan_rejects_bad_id(self):
        with self.assertRaises(hub.HubError):
            hub.plan(self.state, "EP 1", "t", "v.mp4", ["instagram"])

    # --- fill / skip ---------------------------------------------------

    def test_fill_moves_planned_to_filled(self):
        self._plan()
        entry = hub.fill(self.state, "EP-1", "instagram")
        self.assertEqual(entry["status"], "filled")

    def test_skip_then_publish_refused(self):
        self._plan()
        hub.skip(self.state, "EP-1", "instagram", reason="no time")
        with self.assertRaises(hub.HubError):
            hub.publish(self.state, "EP-1", "instagram",
                        "https://example.invalid/a", confirm=True)

    # --- publish -------------------------------------------------------

    def test_publish_auto_platform(self):
        self._plan()
        entry = hub.publish(self.state, "EP-1", "instagram",
                            "https://example.invalid/a",
                            published_at="2026-11-17")
        self.assertEqual(entry["status"], "published")
        self.assertEqual(entry["published_at"], "2026-11-17")

    def test_publish_manual_needs_confirm(self):
        self._plan(plats=("tiktok",))
        with self.assertRaises(hub.HubError):
            hub.publish(self.state, "EP-1", "tiktok",
                        "https://example.invalid/a")
        entry = hub.publish(self.state, "EP-1", "tiktok",
                            "https://example.invalid/a", confirm=True,
                            published_at="2026-11-17")
        self.assertEqual(entry["status"], "published")

    def test_publish_twice_refused(self):
        self._plan()
        hub.publish(self.state, "EP-1", "instagram",
                    "https://example.invalid/a", published_at="2026-11-17")
        with self.assertRaises(hub.HubError):
            hub.publish(self.state, "EP-1", "instagram",
                        "https://example.invalid/b",
                        published_at="2026-11-17")

    def test_publish_without_url_refused(self):
        self._plan()
        with self.assertRaises(hub.HubError):
            hub.publish(self.state, "EP-1", "instagram", "",
                        published_at="2026-11-17")

    def test_dedupe_guard_same_video_same_platform(self):
        self._plan(ep_id="EP-1", video="same.mp4")
        hub.publish(self.state, "EP-1", "instagram",
                    "https://example.invalid/a", published_at="2026-11-17")
        self._plan(ep_id="EP-2", video="same.mp4")
        with self.assertRaises(hub.HubError):
            hub.publish(self.state, "EP-2", "instagram",
                        "https://example.invalid/b",
                        published_at="2026-11-18")

    def test_dedupe_guard_allows_other_platform(self):
        self._plan(ep_id="EP-1", video="same.mp4")
        hub.publish(self.state, "EP-1", "instagram",
                    "https://example.invalid/a", published_at="2026-11-17")
        self._plan(ep_id="EP-2", video="same.mp4")
        entry = hub.publish(self.state, "EP-2", "telegram",
                            "https://example.invalid/c",
                            published_at="2026-11-18")
        self.assertEqual(entry["status"], "published")

    def test_dedupe_guard_allows_different_video(self):
        self._plan(ep_id="EP-1", video="a.mp4")
        hub.publish(self.state, "EP-1", "instagram",
                    "https://example.invalid/a", published_at="2026-11-17")
        self._plan(ep_id="EP-2", video="b.mp4")
        entry = hub.publish(self.state, "EP-2", "instagram",
                            "https://example.invalid/b",
                            published_at="2026-11-18")
        self.assertEqual(entry["status"], "published")

    def test_video_hash_uses_file_bytes(self):
        path = os.path.join(self.tmp, "clip.mp4")
        with open(path, "wb") as fh:
            fh.write(b"fake-video-bytes")
        self.assertEqual(hub.video_hash(path),
                         hub.video_hash(path))
        self.assertNotEqual(hub.video_hash(path),
                            hub.video_hash("clip.mp4"))

    # --- metrics -------------------------------------------------------

    def _published(self, ep_id="EP-1", platform="instagram",
                   published_at="2026-11-10", video=None):
        # Each episode is its own video file; reusing one name across
        # episodes would (correctly) trip the dedupe guard.
        self._plan(ep_id=ep_id, video=video or ("%s.mp4" % ep_id))
        hub.publish(self.state, ep_id, platform,
                    "https://example.invalid/%s" % ep_id,
                    published_at=published_at)

    def test_metrics_require_published(self):
        self._plan()
        with self.assertRaises(hub.HubError):
            hub.add_metrics(self.state, "EP-1", "instagram",
                            "2026-11-10", 10, 1, 0, 0, 100)

    def test_metrics_reject_negative(self):
        self._published()
        with self.assertRaises(hub.HubError):
            hub.add_metrics(self.state, "EP-1", "instagram",
                            "2026-11-10", -5, 0, 0, 0, 100)

    def test_metrics_reject_before_publish(self):
        self._published(published_at="2026-11-10")
        with self.assertRaises(hub.HubError):
            hub.add_metrics(self.state, "EP-1", "instagram",
                            "2026-11-09", 10, 1, 0, 0, 100)

    def test_metrics_same_date_replaces(self):
        self._published()
        hub.add_metrics(self.state, "EP-1", "instagram",
                        "2026-11-10", 100, 10, 1, 1, 1000)
        hub.add_metrics(self.state, "EP-1", "instagram",
                        "2026-11-10", 150, 15, 2, 1, 1010)
        entry = self.state["episodes"]["EP-1"]["platforms"]["instagram"]
        self.assertEqual(len(entry["metrics"]), 1)
        self.assertEqual(entry["metrics"][0]["views"], 150)

    def test_engagement_rate(self):
        sample = {"views": 1000, "likes": 80, "comments": 10,
                  "shares": 10}
        self.assertEqual(hub.engagement_rate(sample), 10.0)
        self.assertIsNone(hub.engagement_rate(
            {"views": 0, "likes": 0, "comments": 0, "shares": 0}))

    # --- review --------------------------------------------------------

    def _seed_two_episodes(self):
        # EP-1 published 2026-11-10, EP-2 published 2026-11-11, instagram.
        self._published(ep_id="EP-1", published_at="2026-11-10")
        for offset, views in ((0, 1000), (1, 1200), (3, 2000), (7, 3000)):
            day = date(2026, 11, 10 + offset).isoformat()
            hub.add_metrics(self.state, "EP-1", "instagram", day, views,
                            views // 10, views // 50, views // 40,
                            10000 + views // 5)
        self._published(ep_id="EP-2", published_at="2026-11-11")
        for offset, views in ((0, 1500), (1, 1800), (3, 2600), (7, 4100)):
            day = date(2026, 11, 11 + offset).isoformat()
            hub.add_metrics(self.state, "EP-2", "instagram", day, views,
                            views // 10, views // 50, views // 40,
                            10000 + views // 5)

    def test_review_day1_values(self):
        self._seed_two_episodes()
        card = hub.review(self.state, "EP-2", 1)
        row = [r for r in card["rows"] if r["platform"] == "instagram"][0]
        self.assertEqual(row["views"], 1800)
        self.assertEqual(row["as_of"], "2026-11-12")
        self.assertEqual(row["engagement_rate"], 10.0 + 2.0 + 2.5)
        self.assertEqual(row["follower_delta"], 60)  # 10360 - 10300

    def test_review_same_age_comparison(self):
        self._seed_two_episodes()
        card = hub.review(self.state, "EP-2", 1)
        row = [r for r in card["rows"] if r["platform"] == "instagram"][0]
        self.assertEqual(row["prev_episode"], "EP-1")
        self.assertEqual(row["prev_views"], 1200)  # EP-1 at day 1
        self.assertEqual(row["views_vs_prev_pct"], 50.0)

    def test_review_first_episode_has_no_comparison(self):
        self._seed_two_episodes()
        card = hub.review(self.state, "EP-1", 3)
        row = [r for r in card["rows"] if r["platform"] == "instagram"][0]
        self.assertNotIn("prev_episode", row)
        self.assertEqual(row["views"], 2000)

    def test_review_notes_unpublished_and_no_metrics(self):
        self._plan(ep_id="EP-9", plats=("instagram", "telegram"))
        hub.publish(self.state, "EP-9", "instagram",
                    "https://example.invalid/x", published_at="2026-11-17")
        card = hub.review(self.state, "EP-9", 1)
        by_platform = {r["platform"]: r for r in card["rows"]}
        self.assertEqual(by_platform["telegram"]["note"],
                         "not published yet")
        self.assertEqual(by_platform["instagram"]["note"], "no metrics yet")

    def test_review_rejects_negative_day(self):
        self._published()
        with self.assertRaises(hub.HubError):
            hub.review(self.state, "EP-1", -1)

    # --- weekly --------------------------------------------------------

    def test_weekly_totals_and_best(self):
        self._seed_two_episodes()
        report = hub.weekly(self.state, as_of="2026-11-16")
        self.assertEqual(report["published"], 2)
        # Latest samples on/before 2026-11-16: EP-1 day 3 = 2000 (day 7 is
        # 2026-11-17, past the end), EP-2 day 3 = 2600.
        self.assertEqual(report["total_views"], 2000 + 2600)
        self.assertEqual(report["best_episode"]["id"], "EP-2")
        self.assertEqual(report["best_platform"]["platform"], "instagram")

    def test_weekly_window_excludes_old_episodes(self):
        self._seed_two_episodes()
        report = hub.weekly(self.state, as_of="2026-11-10")
        self.assertEqual(report["published"], 1)
        self.assertEqual(report["total_views"], 1000)

    def test_weekly_empty_hub(self):
        report = hub.weekly(self.state, as_of="2026-11-17")
        self.assertEqual(report["published"], 0)
        self.assertIsNone(report["best_episode"])
        self.assertIsNone(report["best_platform"])

    # --- check ---------------------------------------------------------

    def test_check_passes_clean_demo(self):
        hub.demo(self.state)
        self.assertEqual(hub.check(self.state), [])

    def test_check_flags_missing_url(self):
        self._published()
        entry = self.state["episodes"]["EP-1"]["platforms"]["instagram"]
        entry["url"] = ""
        failures = hub.check(self.state)
        self.assertTrue(any("without a URL" in f for f in failures))

    def test_check_flags_over_limit_caption(self):
        self._plan()
        entry = self.state["episodes"]["EP-1"]["platforms"]["instagram"]
        entry["caption"] = "x" * 2201
        failures = hub.check(self.state)
        self.assertTrue(any("over the" in f for f in failures))

    def test_check_flags_duplicate_upload(self):
        self._published(ep_id="EP-1")
        # Same video file as EP-1, hand-marked published: the state a
        # bypassed guard (or a hand edit) would leave behind.
        self._plan(ep_id="EP-2", video="EP-1.mp4")
        other = self.state["episodes"]["EP-2"]["platforms"]["instagram"]
        other["status"] = "published"
        other["url"] = "https://example.invalid/b"
        other["published_at"] = "2026-11-11"
        failures = hub.check(self.state)
        self.assertTrue(any("duplicate upload" in f for f in failures))

    # --- demo ----------------------------------------------------------

    def test_demo_is_deterministic_and_idempotent(self):
        first = hub.demo(self.state)
        self.assertEqual(first, ["EP-2026-11-10-01", "EP-2026-11-11-01",
                                 "EP-2026-11-12-01"])
        snapshot = json.dumps(self.state, sort_keys=True)
        second = hub.demo(self.state)
        self.assertEqual(second, [])
        self.assertEqual(json.dumps(self.state, sort_keys=True), snapshot)

    def test_demo_review_day7(self):
        hub.demo(self.state)
        card = hub.review(self.state, "EP-2026-11-12-01", 7)
        row = [r for r in card["rows"] if r["platform"] == "instagram"][0]
        self.assertEqual(row["views"], 4900)
        self.assertEqual(row["prev_episode"], "EP-2026-11-11-01")
        self.assertEqual(row["prev_views"], 4100)

    # --- store ---------------------------------------------------------

    def test_store_roundtrip_and_event_log(self):
        hub.demo(self.state)
        store.save(self.root, self.state)
        store.log_event(self.root, {"kind": "demo", "detail": {}})
        loaded = store.load(self.root)
        self.assertEqual(loaded["episodes"].keys(),
                         self.state["episodes"].keys())
        events = store.read_events(self.root)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "demo")

    def test_store_load_missing_is_empty(self):
        self.assertEqual(store.load(self.root), {"version": 1,
                                                "episodes": {}})

    # --- CLI end to end ------------------------------------------------

    def test_cli_full_flow(self):
        rc = cli.main(["--root", self.root, "demo"])
        self.assertEqual(rc, 0)
        rc = cli.main(["--root", self.root, "review",
                       "EP-2026-11-12-01", "--day", "7"])
        self.assertEqual(rc, 0)
        rc = cli.main(["--root", self.root, "weekly",
                       "--as-of", "2026-11-17"])
        self.assertEqual(rc, 0)
        rc = cli.main(["--root", self.root, "check"])
        self.assertEqual(rc, 0)

    def test_cli_plan_publish_metrics_review(self):
        self.assertEqual(cli.main([
            "--root", self.root, "plan", "EP-2026-11-17-01",
            "--title", "Test episode", "--video", "test.mp4",
            "--platforms", "instagram", "telegram"]), 0)
        self.assertEqual(cli.main([
            "--root", self.root, "publish", "EP-2026-11-17-01",
            "instagram", "--url", "https://example.invalid/ig1",
            "--date", "2026-11-17"]), 0)
        self.assertEqual(cli.main([
            "--root", self.root, "metrics", "EP-2026-11-17-01",
            "instagram", "--date", "2026-11-17",
            "--views", "500", "--likes", "50", "--comments", "5",
            "--shares", "5", "--followers", "12541"]), 0)
        self.assertEqual(cli.main([
            "--root", self.root, "review", "EP-2026-11-17-01",
            "--day", "1"]), 0)
        self.assertEqual(cli.main(["--root", self.root, "check"]), 0)

    def test_cli_publish_manual_without_confirm_fails(self):
        cli.main(["--root", self.root, "plan", "EP-1", "--title", "t",
                  "--video", "v.mp4", "--platforms", "tiktok"])
        rc = cli.main(["--root", self.root, "publish", "EP-1", "tiktok",
                       "--url", "https://example.invalid/a"])
        self.assertEqual(rc, 2)

    def test_cli_check_fails_on_tampered_state(self):
        hub.demo(self.state)
        entry = self.state["episodes"]["EP-2026-11-10-01"] \
            ["platforms"]["instagram"]
        entry["url"] = ""
        store.save(self.root, self.state)
        rc = cli.main(["--root", self.root, "check"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
