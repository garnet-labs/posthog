import pytest
from posthog.test.base import BaseTest

from posthog.models.feature_flag import FeatureFlag
from posthog.models.scoping import get_current_team_context, team_scope, unscoped
from posthog.models.scoping.manager import TeamScopedManager, TeamScopeError
from posthog.models.team import Team


class TestTeamScopedManager(BaseTest):
    def _make_manager(self) -> TeamScopedManager[FeatureFlag]:
        manager: TeamScopedManager[FeatureFlag] = TeamScopedManager()
        manager.model = FeatureFlag  # type: ignore[assignment]
        manager._db = "default"
        return manager

    def test_no_scope_raises_team_scope_error(self):
        with pytest.raises(TeamScopeError, match="No team context set"):
            self._make_manager().get_queryset()

    def test_team_scope_filters_to_team(self):
        other_team = Team.objects.create(organization=self.organization, name="Other Team")

        FeatureFlag.objects.create(team=self.team, key="flag-1", created_by=self.user)
        FeatureFlag.objects.create(team=other_team, key="flag-2", created_by=self.user)

        with team_scope(self.team.id):
            qs = self._make_manager().get_queryset()
            assert qs.count() == 1
            flag = qs.first()
            assert flag is not None
            assert flag.key == "flag-1"

    def test_unscoped_bypasses_context(self):
        other_team = Team.objects.create(organization=self.organization, name="Other Team")

        FeatureFlag.objects.create(team=self.team, key="flag-1", created_by=self.user)
        FeatureFlag.objects.create(team=other_team, key="flag-2", created_by=self.user)

        with team_scope(self.team.id):
            assert self._make_manager().unscoped().count() >= 2

    def test_unscoped_works_without_context(self):
        FeatureFlag.objects.create(team=self.team, key="flag-1", created_by=self.user)
        assert self._make_manager().unscoped().count() >= 1

    def test_for_team_explicit_scoping(self):
        other_team = Team.objects.create(organization=self.organization, name="Other Team")

        FeatureFlag.objects.create(team=self.team, key="flag-1", created_by=self.user)
        FeatureFlag.objects.create(team=other_team, key="flag-2", created_by=self.user)

        qs = self._make_manager().for_team(other_team.id)
        assert qs.count() == 1
        flag = qs.first()
        assert flag is not None
        assert flag.key == "flag-2"

    def test_queryset_chaining_preserves_team_filter(self):
        other_team = Team.objects.create(organization=self.organization, name="Other Team")

        FeatureFlag.objects.create(team=self.team, key="active-flag", active=True, created_by=self.user)
        FeatureFlag.objects.create(team=self.team, key="inactive-flag", active=False, created_by=self.user)
        FeatureFlag.objects.create(team=other_team, key="other-active", active=True, created_by=self.user)

        with team_scope(self.team.id):
            qs = self._make_manager().get_queryset().filter(active=True)
            assert qs.count() == 1
            flag = qs.first()
            assert flag is not None
            assert flag.key == "active-flag"

    def test_unscoped_context_clears_team(self):
        with team_scope(self.team.id):
            from posthog.models.scoping import get_current_team_id

            assert get_current_team_id() == self.team.id

            with unscoped():
                assert get_current_team_id() is None

            assert get_current_team_id() == self.team.id


class TestTeamScopedQuerySet(BaseTest):
    def test_queryset_unscoped_returns_fresh_queryset(self):
        from posthog.models.scoping.manager import TeamScopedQuerySet

        qs: TeamScopedQuerySet[FeatureFlag] = TeamScopedQuerySet(FeatureFlag)
        unscoped_qs = qs.unscoped()
        assert isinstance(unscoped_qs, TeamScopedQuerySet)

    def test_apply_team_filter(self):
        from posthog.models.scoping.manager import TeamScopedQuerySet

        other_team = Team.objects.create(organization=self.organization, name="Other Team")

        FeatureFlag.objects.create(team=self.team, key="flag-1", created_by=self.user)
        FeatureFlag.objects.create(team=other_team, key="flag-2", created_by=self.user)

        qs: TeamScopedQuerySet[FeatureFlag] = TeamScopedQuerySet(FeatureFlag)
        filtered_qs = qs._apply_team_filter(self.team.id)

        assert filtered_qs.count() == 1
        flag = filtered_qs.first()
        assert flag is not None
        assert flag.key == "flag-1"


class TestTeamFilterMixinWithCachedContext(BaseTest):
    def test_cached_parent_team_id_is_used(self):
        parent_team = Team.objects.create(organization=self.organization, name="Parent Team")
        child_team = Team.objects.create(organization=self.organization, name="Child Team", parent_team=parent_team)

        FeatureFlag.objects.create(team=parent_team, key="parent-flag", created_by=self.user)
        FeatureFlag.objects.create(team=child_team, key="child-flag", created_by=self.user)

        with team_scope(child_team.id, parent_team_id=parent_team.id):
            ctx = get_current_team_context()
            assert ctx is not None
            assert ctx.team_id == child_team.id
            assert ctx.parent_team_id == parent_team.id
            assert ctx.effective_team_id == parent_team.id

    def test_effective_team_id_without_parent(self):
        with team_scope(self.team.id):
            ctx = get_current_team_context()
            assert ctx is not None
            assert ctx.team_id == self.team.id
            assert ctx.parent_team_id is None
            assert ctx.effective_team_id == self.team.id
