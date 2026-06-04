import datetime as dt
import unittest

from custom_components.bwt_best_water_home.cron_schedule import next_cron_time, validate_cron_string


class CronScheduleTests(unittest.TestCase):
    def test_daily_two_am_next_same_day(self):
        tz = dt.timezone(dt.timedelta(hours=1))
        now = dt.datetime(2026, 1, 10, 1, 30, tzinfo=tz)
        self.assertEqual(next_cron_time("0 2 * * *", now), dt.datetime(2026, 1, 10, 2, 0, tzinfo=tz))

    def test_daily_two_am_next_day_after_it_passed(self):
        tz = dt.timezone(dt.timedelta(hours=1))
        now = dt.datetime(2026, 1, 10, 2, 1, tzinfo=tz)
        self.assertEqual(next_cron_time("0 2 * * *", now), dt.datetime(2026, 1, 11, 2, 0, tzinfo=tz))

    def test_weekday_field_is_honoured(self):
        now = dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.UTC)  # Thursday
        self.assertEqual(next_cron_time("15 3 * * 1", now), dt.datetime(2026, 1, 5, 3, 15, tzinfo=dt.UTC))

    def test_validate_rejects_invalid_cron(self):
        with self.assertRaises(ValueError):
            validate_cron_string("bad cron")

    def test_validate_accepts_step_hours(self):
        self.assertEqual(validate_cron_string("0 */6 * * *"), "0 */6 * * *")

    def test_validate_accepts_multiple_daily_runs(self):
        self.assertEqual(validate_cron_string("0 1,2 * * *"), "0 1,2 * * *")


if __name__ == "__main__":
    unittest.main()
