import sys
import types

from unittest.mock import MagicMock


def _ensure_django_mocks():
    """Ensure minimal Django mocks exist so ch_migrate can be imported."""
    if "django.conf" not in sys.modules:
        mock_settings = MagicMock()
        mock_settings.CLICKHOUSE_DATABASE = "test_db"

        sys.modules.setdefault("django", types.ModuleType("django"))
        django_conf = types.ModuleType("django.conf")
        django_conf.settings = mock_settings  # type: ignore[attr-defined]
        sys.modules["django.conf"] = django_conf

    if "django.core.management.base" not in sys.modules:

        class FakeBaseCommand:
            def __init__(self):
                self.stdout = MagicMock()

            def print_help(self, *args):
                pass

        sys.modules.setdefault("django.core", types.ModuleType("django.core"))
        sys.modules.setdefault("django.core.management", types.ModuleType("django.core.management"))
        base_mod = types.ModuleType("django.core.management.base")
        base_mod.BaseCommand = FakeBaseCommand  # type: ignore[attr-defined]
        sys.modules["django.core.management.base"] = base_mod

    # Mock posthog.clickhouse.cluster so it can be imported
    if "posthog.clickhouse.cluster" not in sys.modules:
        cluster_mod = types.ModuleType("posthog.clickhouse.cluster")
        cluster_mod.Query = MagicMock  # type: ignore[attr-defined]
        cluster_mod.get_cluster = MagicMock  # type: ignore[attr-defined]
        sys.modules["posthog.clickhouse.cluster"] = cluster_mod


# Set up mocks before any test imports
_ensure_django_mocks()


def _import_ch_migrate():
    """Force re-import of ch_migrate module."""
    sys.modules.pop("posthog.management.commands.ch_migrate", None)
    import posthog.management.commands.ch_migrate as mod

    return mod


class TestHandleStatus:
    def test_status_shows_no_migrations(self):
        mod = _import_ch_migrate()

        mock_settings = MagicMock()
        mock_settings.CLICKHOUSE_DATABASE = "test_db"
        mod.settings = mock_settings  # type: ignore[attr-defined]
        mod.get_cluster = MagicMock()  # type: ignore[attr-defined]
        mod.get_migration_status_all_hosts = MagicMock(return_value={})  # type: ignore[attr-defined]
        mod.get_infi_migration_status = MagicMock(return_value={})  # type: ignore[attr-defined]

        cmd = mod.Command()
        cmd.stdout = MagicMock()
        cmd.handle_status({"node": None})

        output = " ".join(str(c) for c in cmd.stdout.write.call_args_list)
        assert "No migrations" in output

    def test_status_shows_applied_migration(self):
        mod = _import_ch_migrate()

        mock_settings = MagicMock()
        mock_settings.CLICKHOUSE_DATABASE = "test_db"
        mod.settings = mock_settings  # type: ignore[attr-defined]
        mod.get_cluster = MagicMock()  # type: ignore[attr-defined]
        mod.get_migration_status_all_hosts = MagicMock(  # type: ignore[attr-defined]
            return_value={
                "host1:9000": {
                    "reachable": True,
                    "migrations": [
                        (1, "0001_initial", 0, "host1:9000", "up", 1),
                    ],
                },
            }
        )
        mod.get_infi_migration_status = MagicMock(return_value={})  # type: ignore[attr-defined]

        cmd = mod.Command()
        cmd.stdout = MagicMock()
        cmd.handle_status({"node": None})

        output = " ".join(str(c) for c in cmd.stdout.write.call_args_list)
        assert "0001_initial" in output

    def test_status_node_filter(self):
        mod = _import_ch_migrate()

        mock_settings = MagicMock()
        mock_settings.CLICKHOUSE_DATABASE = "test_db"
        mod.settings = mock_settings  # type: ignore[attr-defined]
        mod.get_cluster = MagicMock()  # type: ignore[attr-defined]
        mod.get_migration_status_all_hosts = MagicMock(  # type: ignore[attr-defined]
            return_value={
                "host1:9000": {
                    "reachable": True,
                    "migrations": [
                        (1, "0001_initial", 0, "host1:9000", "up", 1),
                    ],
                },
                "host2:9000": {
                    "reachable": True,
                    "migrations": [
                        (1, "0001_initial", 0, "host2:9000", "up", 1),
                        (2, "0002_events", 0, "host2:9000", "up", 1),
                    ],
                },
            }
        )
        mod.get_infi_migration_status = MagicMock(return_value={})  # type: ignore[attr-defined]

        cmd = mod.Command()
        cmd.stdout = MagicMock()
        cmd.handle_status({"node": "host1:9000"})

        output = " ".join(str(c) for c in cmd.stdout.write.call_args_list)
        assert "host1:9000" in output
        assert "host2:9000" not in output

    def test_status_reads_both_tables(self):
        mod = _import_ch_migrate()

        mock_settings = MagicMock()
        mock_settings.CLICKHOUSE_DATABASE = "test_db"
        mod.settings = mock_settings  # type: ignore[attr-defined]
        mod.get_cluster = MagicMock()  # type: ignore[attr-defined]

        mock_new = MagicMock(
            return_value={
                "host1:9000": {
                    "reachable": True,
                    "migrations": [
                        (5, "0005_new_style", 0, "host1:9000", "up", 1),
                    ],
                },
            }
        )
        mock_infi = MagicMock(
            return_value={
                "host1:9000": {
                    "reachable": True,
                    "migrations": ["0001_initial", "0002_events"],
                },
            }
        )
        mod.get_migration_status_all_hosts = mock_new  # type: ignore[attr-defined]
        mod.get_infi_migration_status = mock_infi  # type: ignore[attr-defined]

        cmd = mod.Command()
        cmd.stdout = MagicMock()
        cmd.handle_status({"node": None})

        mock_new.assert_called_once()
        mock_infi.assert_called_once()

        output = " ".join(str(c) for c in cmd.stdout.write.call_args_list)
        assert "0001_initial" in output
        assert "0005_new_style" in output
