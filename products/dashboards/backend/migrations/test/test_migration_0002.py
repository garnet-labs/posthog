from typing import Any

import pytest
from posthog.test.base import NonAtomicTestMigrations

pytestmark = pytest.mark.skip("old migrations slow overall test run down")


class BackfillDashboardTileTeamTest(NonAtomicTestMigrations):
    migrate_from = "0001_migrate_dashboards_models"
    migrate_to = "0004_dashboardtile_team_not_null"

    CLASS_DATA_LEVEL_SETUP = False

    @property
    def app(self) -> str:
        return "dashboards"

    def setUp(self):
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor

        migrate_from = [
            ("dashboards", self.migrate_from),
            ("posthog", "1079_event_filter_config"),
        ]
        migrate_to = [("dashboards", self.migrate_to)]

        executor = MigrationExecutor(connection)
        old_apps = executor.loader.project_state(migrate_from).apps

        executor.migrate(migrate_from)

        self.setUpBeforeMigration(old_apps)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(migrate_to)

        self.apps = executor.loader.project_state(migrate_to).apps

    def setUpBeforeMigration(self, apps: Any) -> None:
        Organization = apps.get_model("posthog", "Organization")
        Project = apps.get_model("posthog", "Project")
        Team = apps.get_model("posthog", "Team")
        Dashboard = apps.get_model("dashboards", "Dashboard")
        DashboardTile = apps.get_model("dashboards", "DashboardTile")
        Insight = apps.get_model("posthog", "Insight")

        org = Organization.objects.create(name="Test Organization")
        proj = Project.objects.create(id=999999, organization=org, name="Test Project")
        team = Team.objects.create(organization=org, project=proj, name="Test Team")

        dashboard = Dashboard.objects.create(team=team, name="Test Dashboard")
        insight = Insight.objects.create(team=team, name="Test Insight")

        self.tile_id = DashboardTile.objects.create(dashboard=dashboard, insight=insight).id
        self.expected_team_id = team.id

    def test_backfill_populates_team_id(self):
        assert self.apps is not None
        DashboardTile = self.apps.get_model("dashboards", "DashboardTile")
        tile = DashboardTile.objects.get(id=self.tile_id)
        self.assertEqual(tile.team_id, self.expected_team_id)

    def test_team_id_is_not_null(self):
        assert self.apps is not None
        DashboardTile = self.apps.get_model("dashboards", "DashboardTile")
        self.assertEqual(DashboardTile.objects.filter(team_id__isnull=True).count(), 0)
