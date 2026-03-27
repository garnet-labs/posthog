from posthog.test.base import BaseTest

from posthog.models.integration import Integration
from posthog.models.team.team import Team

from products.workflows.backend.models.push_subscription import PushPlatform, PushSubscription


class TestPushSubscription(BaseTest):
    def _create_integration(self, kind: str = "firebase", integration_id: str = "test-project") -> Integration:
        return Integration.objects.create(
            team=self.team,
            kind=kind,
            integration_id=integration_id,
            config={"project_id": integration_id} if kind == "firebase" else {"bundle_id": integration_id},
            sensitive_config={},
        )

    def test_upsert_creates_subscription(self):
        integration = self._create_integration()
        sub = PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="device-token-abc",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )

        assert sub.distinct_id == "user-1"
        assert sub.platform == PushPlatform.ANDROID
        assert sub.integration.id == integration.id
        assert sub.is_active is True
        assert sub.token_hash == PushSubscription._hash_token("device-token-abc")

    def test_upsert_updates_existing_subscription(self):
        integration_fcm = self._create_integration(kind="firebase", integration_id="proj-1")
        integration_apns = self._create_integration(kind="apns", integration_id="com.example.app")

        first = PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="device-token-abc",
            platform=PushPlatform.IOS,
            integration_id=integration_fcm.id,
        )

        second = PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="device-token-abc",
            platform=PushPlatform.IOS,
            integration_id=integration_apns.id,
        )

        assert first.id == second.id
        second.refresh_from_db()
        assert second.integration.id == integration_apns.id

    def test_upsert_different_tokens_creates_separate_subscriptions(self):
        integration = self._create_integration()

        sub1 = PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-a",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )
        sub2 = PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-b",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )

        assert sub1.id != sub2.id

    def test_get_active_tokens_for_distinct_id(self):
        integration = self._create_integration()

        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="active-token",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )
        inactive = PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="inactive-token",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )
        inactive.is_active = False
        inactive.save()

        results = PushSubscription.get_active_tokens_for_distinct_id(self.team.id, "user-1")
        assert len(results) == 1
        assert results[0].token_hash == PushSubscription._hash_token("active-token")

    def test_get_active_tokens_filters_by_platform(self):
        fcm = self._create_integration(kind="firebase", integration_id="proj-1")
        apns = self._create_integration(kind="apns", integration_id="com.example.app")

        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="android-token",
            platform=PushPlatform.ANDROID,
            integration_id=fcm.id,
        )
        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="ios-token",
            platform=PushPlatform.IOS,
            integration_id=apns.id,
        )

        android_only = PushSubscription.get_active_tokens_for_distinct_id(
            self.team.id, "user-1", platform=PushPlatform.ANDROID
        )
        assert len(android_only) == 1
        assert android_only[0].platform == PushPlatform.ANDROID

        ios_only = PushSubscription.get_active_tokens_for_distinct_id(self.team.id, "user-1", platform=PushPlatform.IOS)
        assert len(ios_only) == 1
        assert ios_only[0].platform == PushPlatform.IOS

    def test_get_active_tokens_select_related_integration(self):
        integration = self._create_integration()
        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-1",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )

        results = PushSubscription.get_active_tokens_for_distinct_id(self.team.id, "user-1")

        # integration should be loaded without extra queries
        with self.assertNumQueries(0):
            assert results[0].integration.kind == "firebase"

    def test_deactivate_token(self):
        integration = self._create_integration()
        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-to-deactivate",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )

        count = PushSubscription.deactivate_token(self.team.id, "token-to-deactivate", reason="invalid")
        assert count == 1

        sub = PushSubscription.objects.get(token_hash=PushSubscription._hash_token("token-to-deactivate"))
        assert sub.is_active is False
        assert sub.disabled_reason == "invalid"

    def test_deactivate_token_default_reason(self):
        integration = self._create_integration()
        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-1",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )

        PushSubscription.deactivate_token(self.team.id, "token-1")

        sub = PushSubscription.objects.get(token_hash=PushSubscription._hash_token("token-1"))
        assert sub.disabled_reason == "unregistered"

    def test_deactivate_nonexistent_token_returns_zero(self):
        count = PushSubscription.deactivate_token(self.team.id, "nonexistent-token")
        assert count == 0

    def test_token_hash_kept_in_sync_on_save(self):
        integration = self._create_integration()
        sub = PushSubscription(
            team=self.team,
            distinct_id="user-1",
            token="original-token",
            platform=PushPlatform.ANDROID,
            integration=integration,
        )
        sub.save()

        assert sub.token_hash == PushSubscription._hash_token("original-token")

    def test_team_isolation(self):
        other_team = Team.objects.create(organization=self.organization, name="other team")
        integration = self._create_integration()
        other_integration = Integration.objects.create(
            team=other_team, kind="firebase", integration_id="other-proj", config={}, sensitive_config={}
        )

        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-1",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )
        PushSubscription.upsert_token(
            team_id=other_team.id,
            distinct_id="user-1",
            token="token-2",
            platform=PushPlatform.ANDROID,
            integration_id=other_integration.id,
        )

        results = PushSubscription.get_active_tokens_for_distinct_id(self.team.id, "user-1")
        assert len(results) == 1

    def test_upsert_rejects_integration_from_other_team(self):
        other_team = Team.objects.create(organization=self.organization, name="other team")
        other_integration = Integration.objects.create(
            team=other_team, kind="firebase", integration_id="other-proj", config={}, sensitive_config={}
        )

        with self.assertRaises(ValueError, msg="Integration does not belong to the specified team"):
            PushSubscription.upsert_token(
                team_id=self.team.id,
                distinct_id="user-1",
                token="token-1",
                platform=PushPlatform.ANDROID,
                integration_id=other_integration.id,
            )

        assert PushSubscription.objects.count() == 0

    def test_upsert_reactivates_deactivated_token(self):
        integration = self._create_integration()
        PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-1",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )
        PushSubscription.deactivate_token(self.team.id, "token-1")

        reactivated = PushSubscription.upsert_token(
            team_id=self.team.id,
            distinct_id="user-1",
            token="token-1",
            platform=PushPlatform.ANDROID,
            integration_id=integration.id,
        )

        assert reactivated.is_active is True
        assert reactivated.disabled_reason is None
