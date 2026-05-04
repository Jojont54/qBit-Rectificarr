import unittest
from unittest.mock import mock_open, patch

from main import LOGGER, AppConfig, ArrClient, ConfigCreatedError, build_rename_plan, is_placeholder_config, load_config, normalize_sonarr_pack_source_title, setup_logging, should_fix_item


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

    def test_sonarr_season_pack_supports_1x_episode_tokens(self):
        plan = build_rename_plan(
            "sonarr",
            "Rooster.S01.MULTi.VFF.1080p.WEB.EAC3.5.1.H265-FW",
            [
                {"name": "Rooster.1x01.MULTi.1080p.WEB.H265-FW/Rooster.1x01.mkv"},
                {"name": "Rooster.1x02.MULTi.1080p.WEB.H265-FW/Rooster.1x02.mkv"},
            ],
        )

        self.assertEqual(plan, [
            (
                "Rooster.1x01.MULTi.1080p.WEB.H265-FW/Rooster.1x01.mkv",
                "Rooster.1x01.MULTi.1080p.WEB.H265-FW/Rooster.S01E01.MULTi.VFF.1080p.WEB.EAC3.5.1.H265-FW.mkv",
            ),
            (
                "Rooster.1x02.MULTi.1080p.WEB.H265-FW/Rooster.1x02.mkv",
                "Rooster.1x02.MULTi.1080p.WEB.H265-FW/Rooster.S01E02.MULTi.VFF.1080p.WEB.EAC3.5.1.H265-FW.mkv",
            ),
        ])

    def test_sonarr_pack_keeps_each_file_episode_when_source_title_has_single_episode(self):
        plan = build_rename_plan(
            "sonarr",
            "High.Potential.S02E11.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW",
            [
                {
                    "name": (
                        "High.Potential.S02.MULTi.1080p.WEB.H264-FW/"
                        "High.Potential.S02E01.MULTi.1080p.WEB.H264-FW/"
                        "High.Potential.S02E01.MULTi.1080p.WEB.H264-FW.mkv"
                    )
                },
                {
                    "name": (
                        "High.Potential.S02.MULTi.1080p.WEB.H264-FW/"
                        "High.Potential.S02E02.MULTi.1080p.WEB.H264-FW/"
                        "High.Potential.S02E02.MULTi.1080p.WEB.H264-FW.mkv"
                    )
                },
            ],
        )

        self.assertEqual(plan, [
            (
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E01.MULTi.1080p.WEB.H264-FW/High.Potential.S02E01.MULTi.1080p.WEB.H264-FW.mkv",
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E01.MULTi.1080p.WEB.H264-FW/High.Potential.S02E01.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW.mkv",
            ),
            (
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E02.MULTi.1080p.WEB.H264-FW.mkv",
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E02.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW.mkv",
            ),
        ])

    def test_sonarr_pack_source_episode_is_normalized_to_season_template(self):
        self.assertEqual(
            normalize_sonarr_pack_source_title("High.Potential.S02E11.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW"),
            "High.Potential.S02.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW",
        )

    def test_sonarr_episode_folder_token_is_used_when_file_name_has_no_episode(self):
        plan = build_rename_plan(
            "sonarr",
            "High.Potential.S02E11.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW",
            [
                {
                    "name": (
                        "High.Potential.S02.MULTi.1080p.WEB.H264-FW/"
                        "High.Potential.S02E01.MULTi.1080p.WEB.H264-FW/"
                        "video.mkv"
                    )
                },
                {
                    "name": (
                        "High.Potential.S02.MULTi.1080p.WEB.H264-FW/"
                        "High.Potential.S02E02.MULTi.1080p.WEB.H264-FW/"
                        "video.mkv"
                    )
                },
            ],
        )

        self.assertEqual(plan, [
            (
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E01.MULTi.1080p.WEB.H264-FW/video.mkv",
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E01.MULTi.1080p.WEB.H264-FW/High.Potential.S02E01.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW.mkv",
            ),
            (
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E02.MULTi.1080p.WEB.H264-FW/video.mkv",
                "High.Potential.S02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E02.MULTi.1080p.WEB.H264-FW/High.Potential.S02E02.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW.mkv",
            ),
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
                    patch("logging.handlers.RotatingFileHandler"):
                setup_logging()

            makedirs.assert_called_once_with("/config/logs", exist_ok=True)
        finally:
            LOGGER.handlers.clear()

    def test_placeholder_config_is_detected(self):
        self.assertTrue(is_placeholder_config({"qbittorrent": {"host": "your_qbittorrent_host"}}))
        self.assertFalse(is_placeholder_config({"qbittorrent": {"host": "192.168.1.10"}}))

    def test_sonarr_source_title_prefers_richer_matching_history_release(self):
        client = ArrClient.__new__(ArrClient)
        client.config = AppConfig("sonarr", "sonarr", "sonarr", "8989", "api")
        client.history_for = lambda item: [
            {
                "downloadId": "abc",
                "sourceTitle": "High.Potential.S02.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW",
            }
        ]
        item = {
            "downloadId": "abc",
            "title": "High.Potential.S02.MULTi.1080p.WEB.H264-FW",
            "statusMessages": [{
                "messages": ["Not a Custom Format upgrade for existing episode file(s). New: [Season Pack]"],
            }],
        }

        self.assertEqual(
            client.source_title(item),
            "High.Potential.S02.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW",
        )

    def test_sonarr_source_title_beats_richer_non_source_title(self):
        client = ArrClient.__new__(ArrClient)
        client.config = AppConfig("sonarr", "sonarr", "sonarr", "8989", "api")
        client.history_for = lambda item: [
            {
                "downloadId": "abc",
                "sourceTitle": "High.Potential.S02.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW",
                "title": "Wrong.Title.S02.MULTi.VFF.2160p.WEB.EAC3.7.1.H265-GROUP",
            }
        ]
        item = {
            "downloadId": "abc",
            "sourceTitle": "Poor.Queue.Title.S02.MULTi.1080p.WEB.H264-FW",
            "statusMessages": [{
                "messages": ["Not a Custom Format upgrade for existing episode file(s). New: [Season Pack]"],
            }],
        }

        self.assertEqual(
            client.source_title(item),
            "High.Potential.S02.MULTi.VFF.1080p.WEB.EAC3.5.1.H264-FW",
        )

    def test_not_custom_format_upgrade_is_fixed_even_when_not_import_pending(self):
        item = {
            "trackedDownloadState": "importBlocked",
            "trackedDownloadStatus": "warning",
            "statusMessages": [{
                "title": "Release Rejected",
                "messages": ["Not a Custom Format upgrade for existing episode file(s)."],
            }],
        }

        self.assertTrue(should_fix_item(item))


if __name__ == "__main__":
    unittest.main()
