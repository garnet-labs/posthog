from posthog.test.base import BaseTest

from parameterized import parameterized

from products.notebooks.backend.collab import get_steps_since, initialize_collab_session, submit_steps


class TestNotebookCollab(BaseTest):
    def test_initialize_collab_session_sets_version(self):
        version = initialize_collab_session("nb1", 5)
        assert version == 5

    def test_initialize_collab_session_returns_existing_version(self):
        initialize_collab_session("nb2", 5)
        # Submit a step to advance the version
        submit_steps("nb2", "client1", [{"stepType": "replace", "from": 0, "to": 0}], 5)
        # Re-initializing should return the advanced version, not overwrite
        version = initialize_collab_session("nb2", 5)
        assert version == 6

    def test_submit_steps_accepted(self):
        initialize_collab_session("nb3", 0)
        result = submit_steps("nb3", "client1", [{"stepType": "replace", "from": 0, "to": 0}], 0)
        assert result.accepted is True
        assert result.version == 1

    def test_submit_steps_rejected_on_version_mismatch(self):
        initialize_collab_session("nb4", 0)
        # First client advances the version
        submit_steps("nb4", "client1", [{"stepType": "replace", "from": 0, "to": 0}], 0)
        # Second client tries with stale version
        result = submit_steps("nb4", "client2", [{"stepType": "replace", "from": 1, "to": 1}], 0)
        assert result.accepted is False
        assert result.version == 1
        assert result.steps_since is not None
        assert len(result.steps_since) == 1

    def test_submit_multiple_steps(self):
        initialize_collab_session("nb5", 0)
        steps = [
            {"stepType": "replace", "from": 0, "to": 0},
            {"stepType": "replace", "from": 1, "to": 1},
            {"stepType": "replace", "from": 2, "to": 2},
        ]
        result = submit_steps("nb5", "client1", steps, 0)
        assert result.accepted is True
        assert result.version == 3

    def test_get_steps_since(self):
        initialize_collab_session("nb6", 0)
        submit_steps("nb6", "client1", [{"stepType": "replace", "from": 0, "to": 0}], 0)
        submit_steps("nb6", "client1", [{"stepType": "replace", "from": 1, "to": 1}], 1)
        submit_steps("nb6", "client1", [{"stepType": "replace", "from": 2, "to": 2}], 2)

        version, steps = get_steps_since("nb6", 1)
        assert version == 3
        assert len(steps) == 2

    def test_get_steps_since_no_new_steps(self):
        initialize_collab_session("nb7", 0)
        submit_steps("nb7", "client1", [{"stepType": "replace", "from": 0, "to": 0}], 0)

        version, steps = get_steps_since("nb7", 1)
        assert version == 1
        assert len(steps) == 0

    def test_get_steps_since_uninitalized(self):
        version, steps = get_steps_since("nonexistent", 0)
        assert version == 0
        assert len(steps) == 0

    def test_submit_to_uninitialized_session(self):
        result = submit_steps("uninitialized", "client1", [{"stepType": "replace"}], 0)
        assert result.accepted is False
        assert result.version == 0

    @parameterized.expand(
        [
            ("two_clients_sequential", 2),
            ("three_clients_sequential", 3),
        ]
    )
    def test_multiple_clients_sequential(self, _name, num_clients):
        initialize_collab_session("nb_multi", 0)
        expected_version = 0
        for i in range(num_clients):
            result = submit_steps(
                "nb_multi",
                f"client{i}",
                [{"stepType": "replace", "from": i, "to": i}],
                expected_version,
            )
            assert result.accepted is True
            expected_version += 1

        assert expected_version == num_clients
        version, steps = get_steps_since("nb_multi", 0)
        assert version == num_clients
        assert len(steps) == num_clients
