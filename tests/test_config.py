from unittest import TestCase
from unittest.mock import patch

from billing_collector.config import Settings


class SettingsTests(TestCase):
    def test_settings_parse_required_and_csv_environment(self):
        with patch.dict(
            "os.environ",
            {
                "SCW_SECRET_KEY": "secret",
                "SCW_ORGANIZATION_ID": "org-a",
                "BILLING_COLLECTOR_PROJECT_IDS": "project-a, project-b",
                "BILLING_COLLECTOR_CATEGORY_NAMES": "Compute,Storage",
                "BILLING_COLLECTOR_BIND_PORT": "9600",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.scw_secret_key, "secret")
        self.assertEqual(settings.scw_organization_id, "org-a")
        self.assertEqual(settings.project_ids, ("project-a", "project-b"))
        self.assertEqual(settings.category_names, ("Compute", "Storage"))
        self.assertEqual(settings.bind_port, 9600)

    def test_settings_reports_missing_required_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "SCW_SECRET_KEY"):
                Settings.from_env()

