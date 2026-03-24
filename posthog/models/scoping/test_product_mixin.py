from django.test import SimpleTestCase

from posthog.models.scoping import team_scope, unscoped
from posthog.models.scoping.product_mixin import ProductTeamManager, ProductTeamQuerySet


class TestProductTeamQuerySet(SimpleTestCase):
    def test_unscoped_returns_fresh_queryset(self) -> None:
        from products.visual_review.backend.models import Repo

        qs = ProductTeamQuerySet(model=Repo)
        unscoped_qs = qs.unscoped()
        self.assertIsInstance(unscoped_qs, ProductTeamQuerySet)
        self.assertIsNot(qs, unscoped_qs)


class TestProductTeamManagerScoping(SimpleTestCase):
    """Test that the manager respects ContextVar team scoping."""

    def test_no_context_returns_unfiltered(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        qs = mgr.get_queryset()
        # No team context set — queryset has no WHERE clause for team_id
        self.assertFalse(qs.query.has_filters())

    def test_with_context_filters_by_team(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        with team_scope(42):
            qs = mgr.get_queryset()
            self.assertTrue(qs.query.has_filters())

    def test_unscoped_context_manager_bypasses_filter(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        with team_scope(42):
            with unscoped():
                qs = mgr.get_queryset()
                self.assertFalse(qs.query.has_filters())

    def test_for_team_explicit_scoping(self) -> None:
        from products.visual_review.backend.models import Repo

        mgr = ProductTeamManager()
        mgr.model = Repo
        mgr.auto_created = True
        # Use team_scope so _resolve_effective_team_id uses context cache
        # instead of hitting the DB
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
