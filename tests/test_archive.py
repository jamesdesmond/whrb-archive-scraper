import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import main


class ArchiveTests(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(main.sanitize_filename("Bad/Name:*"), "BadName")

    def test_find_show_for_hour(self):
        tz = ZoneInfo("America/New_York")
        schedule = [
            {
                "title": "Morning Show",
                "start": datetime(2026, 1, 29, 6, 0, tzinfo=tz),
                "end": datetime(2026, 1, 29, 10, 0, tzinfo=tz),
            },
            {
                "title": "Midday",
                "start": datetime(2026, 1, 29, 10, 0, tzinfo=tz),
                "end": datetime(2026, 1, 29, 14, 0, tzinfo=tz),
            },
        ]
        hour_local = datetime(2026, 1, 29, 7, 0, tzinfo=tz)
        self.assertEqual(main.find_show_for_hour(hour_local, schedule), "Morning Show")

    def test_build_hourly_entries_count(self):
        schedule = []
        entries = main.build_hourly_entries(1, schedule, now_utc=datetime(2026, 1, 29, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(len(entries), 24)

    def test_parse_playlist(self):
        playlist = """#EXTM3U
#EXTINF:10,
000.ts
#EXTINF:10,
001.ts
"""
        urls = main.parse_playlist(playlist, "https://stream.whrb.org/archive/2026_01_27_00/")
        self.assertEqual(
            urls,
            [
                "https://stream.whrb.org/archive/2026_01_27_00/000.ts",
                "https://stream.whrb.org/archive/2026_01_27_00/001.ts",
            ],
        )

    def test_weekly_fallback_match(self):
        tz = ZoneInfo("America/New_York")
        schedule = [
            {
                "title": "Weekly Show",
                "start": datetime(2026, 1, 30, 9, 0, tzinfo=tz),
                "end": datetime(2026, 1, 30, 11, 0, tzinfo=tz),
            }
        ]
        past_hour = datetime(2026, 1, 23, 9, 30, tzinfo=tz)
        self.assertEqual(main.find_show_for_hour(past_hour, schedule), "Weekly Show")

    def test_iter_archive_hours(self):
        tz = ZoneInfo("America/New_York")
        start_local = datetime(2026, 1, 29, 22, 0, tzinfo=tz)
        end_local = datetime(2026, 1, 30, 1, 0, tzinfo=tz)
        hours = main.iter_archive_hours(start_local, end_local)
        self.assertEqual(len(hours), 3)

    def test_extract_calendar_ical_url(self):
        html = (
            "<iframe src=\"https://www.google.com/calendar/embed?showTitle=0&src=test%40group.calendar.google.com&ctz=America%2FNew_York\"></iframe>"
        )
        ical = main.extract_calendar_ical_url(html)
        self.assertEqual(
            ical,
            "https://calendar.google.com/calendar/ical/test%40group.calendar.google.com/public/basic.ics",
        )

    def test_build_show_blocks_dedupes(self):
        tz = ZoneInfo("America/New_York")
        start = datetime(2026, 1, 30, 9, 0, tzinfo=tz)
        end = datetime(2026, 1, 30, 12, 0, tzinfo=tz)
        blocks = [
            {"title": "Afternoon Concert", "start": start, "end": end},
            {"title": "Afternoon Concert", "start": start, "end": end},
        ]
        results = main.build_show_blocks(1, blocks, now_utc=datetime(2026, 1, 30, 20, 0, tzinfo=timezone.utc))
        self.assertEqual(len(results), 1)

    def test_build_show_blocks_skips_partial(self):
        tz = ZoneInfo("America/New_York")
        now_utc = datetime(2026, 1, 30, 20, 0, tzinfo=timezone.utc)
        range_end = now_utc.astimezone(tz)
        range_start = range_end - timedelta(days=1)
        blocks = [
            {
                "title": "In Progress",
                "start": range_end - timedelta(hours=1),
                "end": range_end + timedelta(hours=1),
            },
            {
                "title": "Too Old",
                "start": range_start - timedelta(hours=1),
                "end": range_start + timedelta(hours=1),
            },
            {
                "title": "Full Show",
                "start": range_end - timedelta(hours=4),
                "end": range_end - timedelta(hours=2),
            },
        ]
        results = main.build_show_blocks(1, blocks, now_utc=now_utc)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Full Show")


if __name__ == "__main__":
    unittest.main()
