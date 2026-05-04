import unittest
from unittest.mock import mock_open, patch

from main import LOGGER, ConfigCreatedError, build_rename_plan, load_config, setup_logging


class RenamePlanTests(unittest.TestCase):
    def test_radarr_renames_main_video_and_associated_subtitle(self):
        plan = build_rename_plan(
            "radarr",
            "Nom.Release.2024.MULTI.VFF.1080p.WEBRip.x265-GROUP",
            [
                {"name": "movie.mkv"},
                {"name": "movie.fr.srt"},
                {"name": "sample.mkv"},
            ],
        )

        self.assertEqual(plan, [
            ("movie.mkv", "Nom.Release.2024.MULTI.VFF.1080p.WEBRip.x265-GROUP.mkv"),
            ("movie.fr.srt", "Nom.Release.2024.MULTI.VFF.1080p.WEBRip.x265-GROUP.fr.srt"),
        ])

    def test_sonarr_season_pack_injects_episode_number(self):
        plan = build_rename_plan(
            "sonarr",
            "Brooklyn.Nine.Nine.S01.MULTI.VFF.1080p.WEBRip.AC3.5.1.x265-P2P",
            [
                {"name": "Brooklyn Nine-Nine S01E01 Pilot.mkv"},
                {"name": "Brooklyn Nine-Nine S01E02 The Tagger.mkv"},
                {"name": "Brooklyn Nine-Nine S01E03 The Slump.mkv"},
            ],
        )

        self.assertEqual(plan, [
            (
                "Brooklyn Nine-Nine S01E01 Pilot.mkv",
                "Brooklyn.Nine.Nine.S01E01.MULTI.VFF.1080p.WEBRip.AC3.5.1.x265-P2P.mkv",
            ),
            (
                "Brooklyn Nine-Nine S01E02 The Tagger.mkv",
                "Brooklyn.Nine.Nine.S01E02.MULTI.VFF.1080p.WEBRip.AC3.5.1.x265-P2P.mkv",
            ),
            (
                "Brooklyn Nine-Nine S01E03 The Slump.mkv",
                "Brooklyn.Nine.Nine.S01E03.MULTI.VFF.1080p.WEBRip.AC3.5.1.x265-P2P.mkv",
            ),
        ])

    def test_sonarr_single_episode_uses_source_title(self):
        plan = build_rename_plan(
            "sonarr",
            "Brooklyn.Nine.Nine.S01E22.MULTI.VFF.1080p.WEBRip.AC3.5.1.x265-P2P",
            [{"name": "Episode22.mkv"}],
        )

        self.assertEqual(plan, [
            (
                "Episode22.mkv",
                "Brooklyn.Nine.Nine.S01E22.MULTI.VFF.1080p.WEBRip.AC3.5.1.x265-P2P.mkv",
            )
        ])

    def test_sonarr_skips_pack_file_without_episode_number(self):
        plan = build_rename_plan(
            "sonarr",
            "Brooklyn.Nine.Nine.S01.MULTI.VFF.1080p.WEBRip.AC3.5.1.x265-P2P",
            [{"name": "Episode22.mkv"}],
        )

        self.assertEqual(plan, [])

    def test_radarr_renames_only_largest_video_when_multiple_remain(self):
        plan = build_rename_plan(
            "radarr",
            "Nom.Release.2024.MULTI.VFF.1080p.WEBRip.x265-GROUP",
            [
                {"name": "bonus.mkv", "size": 100},
                {"name": "feature.mkv", "size": 1000},
            ],
        )

        self.assertEqual(plan, [
            ("feature.mkv", "Nom.Release.2024.MULTI.VFF.1080p.WEBRip.x265-GROUP.mkv"),
        ])

    def test_sonarr_does_not_skip_episode_just_because_title_contains_sample(self):
        plan = build_rename_plan(
            "sonarr",
            "Some.Show.S01.MULTI.1080p.WEBRip.x265-GROUP",
            [{"name": "Some Show S01E03 Sample.mkv", "size": 1000}],
        )

        self.assertEqual(plan, [
            ("Some Show S01E03 Sample.mkv", "Some.Show.S01E03.MULTI.1080p.WEBRip.x265-GROUP.mkv"),
        ])

    def test_missing_config_is_created(self):
        with patch("main.os.path.exists", return_value=False), \
                patch("main.os.makedirs") as makedirs, \
                patch("builtins.open", mock_open()):
            with self.assertRaises(ConfigCreatedError):
                load_config("/config/config.json")

        makedirs.assert_called_once_with("/config", exist_ok=True)

    def test_logging_creates_log_directory(self):
        try:
            with patch.dict("main.os.environ", {"LOG_FILE": "/config/logs/qbit-rectificarr.log"}), \
                    patch("main.os.makedirs") as makedirs, \
                    patch("logging.FileHandler"):
                setup_logging()

            makedirs.assert_called_once_with("/config/logs", exist_ok=True)
        finally:
            LOGGER.handlers.clear()


if __name__ == "__main__":
    unittest.main()
