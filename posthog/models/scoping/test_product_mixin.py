import pytest

from django.test import SimpleTestCase

from posthog.models.scoping import team_scope, unscoped
from posthog.models.scoping.manager import TeamScopeError
from posthog.models.scoping.product_mixin import ProductTeamManager, ProductTeamQuerySet


class TestProductTeamQuerySet(SimpleTestCase):
    def test_unscoped_returns_fresh_queryset(self) -> None:
        from products.visual_review.backend.models import Repo

        qs = ProductTeamQuerySet(model=Repo)
        unscoped_qs = qs.unscoped()
        self.assertIsInstance(unscoped_qs, ProductTeamQuerySet)
        self.assertIsNot(qs, unscoped_qs)


class TestProductTeamManagerScoping(SimpleTestCase):
    def test_no_context_raises_team_scope_error(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        with pytest.raises(TeamScopeError, match="No team context set"):
            mgr.get_queryset()

    def test_with_context_filters_by_team(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        with team_scope(42):
            qs = mgr.get_queryset()
            self.assertTrue(qs.query.has_filters())

    def test_unscoped_context_manager_raises_without_scope(self) -> None:
        """unscoped() context manager clears team context — manager should raise."""
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        with team_scope(42):
            with unscoped():
                with pytest.raises(TeamScopeError):
                    mgr.get_queryset()

    def test_for_team_explicit_scoping(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        with team_scope(99):
            qs = mgr.for_team(99)
            self.assertTrue(qs.query.has_filters())

    def test_unscoped_manager_returns_unfiltered(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        with team_scope(42):
            qs = mgr.unscoped()
            self.assertFalse(qs.query.has_filters())

    def test_unscoped_manager_works_without_context(self) -> None:
        """unscoped() does not raise even without team context."""
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        qs = mgr.unscoped()
        self.assertFalse(qs.query.has_filters())
