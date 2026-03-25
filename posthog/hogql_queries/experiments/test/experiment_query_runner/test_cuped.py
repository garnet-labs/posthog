from datetime import datetime
from typing import cast

from freezegun import freeze_time
from posthog.test.base import _create_event, _create_person, flush_persons_and_events

from django.test import override_settings

from posthog.schema import (
    EventsNode,
    ExperimentFunnelMetric,
    ExperimentMeanMetric,
    ExperimentMetricMathType,
    ExperimentQuery,
    ExperimentQueryResponse,
    FunnelConversionWindowTimeUnit,
)

from posthog.hogql_queries.experiments.experiment_query_runner import ExperimentQueryRunner
from posthog.hogql_queries.experiments.test.experiment_query_runner.base import ExperimentQueryRunnerBaseTest


@override_settings(IN_UNIT_TESTING=True)
class TestExperimentCuped(ExperimentQueryRunnerBaseTest):
    @freeze_time("2020-01-20T12:00:00Z")
    def test_mean_metric_cuped_collects_pre_exposure_data(self):
        """CUPED query collects pre-exposure metric values as covariates."""
        feature_flag = self.create_feature_flag()
        experiment = self.create_experiment(
            feature_flag=feature_flag,
            start_date=datetime(2020, 1, 10, 0, 0, 0),
            end_date=datetime(2020, 1, 20, 0, 0, 0),
        )
        experiment.stats_config = {
            "method": "frequentist",
            "cuped": {"enabled": True, "lookback_days": 7},
        }
        experiment.save()

        metric = ExperimentMeanMetric(
            source=EventsNode(
                event="purchase",
                math=ExperimentMetricMathType.SUM,
                math_property="amount",
            ),
        )

        feature_flag_property = f"$feature/{feature_flag.key}"

        # User 1 (control): pre-exposure purchase of 5, post-exposure purchase of 10
        _create_person(distinct_ids=["user_1"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_1",
            timestamp="2020-01-08T12:00:00Z",  # pre-exposure (within 7-day lookback)
            properties={feature_flag_property: "control", "amount": 5},
        )
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_1",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "control",
                "$feature_flag_response": "control",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_1",
            timestamp="2020-01-12T12:00:00Z",  # post-exposure
            properties={feature_flag_property: "control", "amount": 10},
        )

        # User 2 (control): no pre-exposure purchase, post-exposure purchase of 8
        _create_person(distinct_ids=["user_2"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_2",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "control",
                "$feature_flag_response": "control",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_2",
            timestamp="2020-01-12T12:00:00Z",
            properties={feature_flag_property: "control", "amount": 8},
        )

        # User 3 (test): pre-exposure purchase of 12, post-exposure purchase of 20
        _create_person(distinct_ids=["user_3"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_3",
            timestamp="2020-01-09T12:00:00Z",  # pre-exposure
            properties={feature_flag_property: "test", "amount": 12},
        )
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_3",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "test",
                "$feature_flag_response": "test",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_3",
            timestamp="2020-01-13T12:00:00Z",
            properties={feature_flag_property: "test", "amount": 20},
        )

        # User 4 (test): pre-exposure purchase TOO EARLY (outside lookback), post-exposure purchase of 15
        _create_person(distinct_ids=["user_4"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_4",
            timestamp="2020-01-01T12:00:00Z",  # too early, outside 7-day lookback
            properties={feature_flag_property: "test", "amount": 100},
        )
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_4",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "test",
                "$feature_flag_response": "test",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_4",
            timestamp="2020-01-14T12:00:00Z",
            properties={feature_flag_property: "test", "amount": 15},
        )

        flush_persons_and_events()

        experiment_query = ExperimentQuery(
            experiment_id=experiment.id,
            kind="ExperimentQuery",
            metric=metric,
        )

        query_runner = ExperimentQueryRunner(query=experiment_query, team=self.team)
        result = cast(ExperimentQueryResponse, query_runner.calculate())

        control = result.baseline
        assert control is not None
        test_variant = result.variant_results[0]

        # Post-exposure stats: control sum=10+8=18, test sum=20+15=35
        self.assertEqual(control.sum, 18)
        self.assertEqual(test_variant.sum, 35)
        self.assertEqual(control.number_of_samples, 2)
        self.assertEqual(test_variant.number_of_samples, 2)

        # Pre-exposure covariate: control user_1 has 5, user_2 has 0 → sum=5
        # test user_3 has 12, user_4 has 0 (too early) → sum=12
        assert control.covariate_sum is not None
        self.assertEqual(control.covariate_sum, 5)
        self.assertEqual(test_variant.covariate_sum, 12)

        # Cross-product: control user_1: 10*5=50, user_2: 8*0=0 → sum=50
        # test user_3: 20*12=240, user_4: 15*0=0 → sum=240
        assert control.main_covariate_sum_product is not None
        self.assertEqual(control.main_covariate_sum_product, 50)
        self.assertEqual(test_variant.main_covariate_sum_product, 240)

    @freeze_time("2020-01-20T12:00:00Z")
    def test_mean_metric_without_cuped_has_no_covariate_fields(self):
        """When CUPED is disabled, no covariate fields are returned."""
        feature_flag = self.create_feature_flag()
        experiment = self.create_experiment(
            feature_flag=feature_flag,
            start_date=datetime(2020, 1, 10, 0, 0, 0),
            end_date=datetime(2020, 1, 20, 0, 0, 0),
        )
        experiment.stats_config = {"method": "frequentist"}
        experiment.save()

        metric = ExperimentMeanMetric(
            source=EventsNode(
                event="purchase",
                math=ExperimentMetricMathType.SUM,
                math_property="amount",
            ),
        )

        feature_flag_property = f"$feature/{feature_flag.key}"

        _create_person(distinct_ids=["user_1"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_1",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "control",
                "$feature_flag_response": "control",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_1",
            timestamp="2020-01-12T12:00:00Z",
            properties={feature_flag_property: "control", "amount": 10},
        )

        _create_person(distinct_ids=["user_2"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_2",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "test",
                "$feature_flag_response": "test",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_2",
            timestamp="2020-01-12T12:00:00Z",
            properties={feature_flag_property: "test", "amount": 15},
        )

        flush_persons_and_events()

        experiment_query = ExperimentQuery(
            experiment_id=experiment.id,
            kind="ExperimentQuery",
            metric=metric,
        )

        query_runner = ExperimentQueryRunner(query=experiment_query, team=self.team)
        result = cast(ExperimentQueryResponse, query_runner.calculate())

        assert result.baseline is not None
        assert result.baseline.covariate_sum is None

    @freeze_time("2020-01-20T12:00:00Z")
    def test_funnel_metric_cuped_collects_pre_exposure_conversion(self):
        """CUPED funnel query detects pre-exposure completion of the last funnel step."""
        feature_flag = self.create_feature_flag()
        experiment = self.create_experiment(
            feature_flag=feature_flag,
            start_date=datetime(2020, 1, 10, 0, 0, 0),
            end_date=datetime(2020, 1, 20, 0, 0, 0),
        )
        experiment.stats_config = {
            "method": "frequentist",
            "cuped": {"enabled": True, "lookback_days": 7},
        }
        experiment.save()

        metric = ExperimentFunnelMetric(
            series=[
                EventsNode(event="view_product", name="view_product"),
                EventsNode(event="purchase", name="purchase"),
            ],
            conversion_window=7,
            conversion_window_unit=FunnelConversionWindowTimeUnit.DAY,
        )

        feature_flag_property = f"$feature/{feature_flag.key}"

        # User 1 (control): purchased before exposure → pre_value=1, converts after → post_value=1
        _create_person(distinct_ids=["user_1"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_1",
            timestamp="2020-01-08T12:00:00Z",  # pre-exposure purchase
            properties={feature_flag_property: "control"},
        )
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_1",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "control",
                "$feature_flag_response": "control",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="view_product",
            distinct_id="user_1",
            timestamp="2020-01-12T12:00:00Z",
            properties={feature_flag_property: "control"},
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_1",
            timestamp="2020-01-12T12:01:00Z",
            properties={feature_flag_property: "control"},
        )

        # User 2 (control): no pre-exposure purchase → pre_value=0, does not convert → post_value=0
        _create_person(distinct_ids=["user_2"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_2",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "control",
                "$feature_flag_response": "control",
                "$feature_flag": feature_flag.key,
            },
        )

        # User 3 (test): no pre-exposure purchase, converts after
        _create_person(distinct_ids=["user_3"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_3",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "test",
                "$feature_flag_response": "test",
                "$feature_flag": feature_flag.key,
            },
        )
        _create_event(
            team=self.team,
            event="view_product",
            distinct_id="user_3",
            timestamp="2020-01-12T12:00:00Z",
            properties={feature_flag_property: "test"},
        )
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_3",
            timestamp="2020-01-12T12:01:00Z",
            properties={feature_flag_property: "test"},
        )

        # User 4 (test): purchased before exposure, does not convert after
        _create_person(distinct_ids=["user_4"], team_id=self.team.pk)
        _create_event(
            team=self.team,
            event="purchase",
            distinct_id="user_4",
            timestamp="2020-01-09T12:00:00Z",  # pre-exposure purchase
            properties={feature_flag_property: "test"},
        )
        _create_event(
            team=self.team,
            event="$feature_flag_called",
            distinct_id="user_4",
            timestamp="2020-01-11T12:00:00Z",
            properties={
                feature_flag_property: "test",
                "$feature_flag_response": "test",
                "$feature_flag": feature_flag.key,
            },
        )

        flush_persons_and_events()

        experiment_query = ExperimentQuery(
            experiment_id=experiment.id,
            kind="ExperimentQuery",
            metric=metric,
        )

        query_runner = ExperimentQueryRunner(query=experiment_query, team=self.team)
        result = cast(ExperimentQueryResponse, query_runner.calculate())

        control = result.baseline
        assert control is not None
        test_variant = result.variant_results[0]

        # Control: user_1 converted, user_2 did not → sum=1
        self.assertEqual(control.number_of_samples, 2)
        self.assertEqual(control.sum, 1)

        # Test: user_3 converted, user_4 did not → sum=1
        self.assertEqual(test_variant.number_of_samples, 2)
        self.assertEqual(test_variant.sum, 1)

        # Pre-exposure covariate (binary: did user perform last step before exposure?)
        # Control: user_1 purchased before → 1, user_2 did not → 0, sum=1
        # Test: user_3 did not purchase before → 0, user_4 purchased before → 1, sum=1
        assert control.covariate_sum is not None
        self.assertEqual(control.covariate_sum, 1)
        self.assertEqual(test_variant.covariate_sum, 1)

        # Cross-product (post_conversion * pre_conversion):
        # Control: user_1: 1*1=1, user_2: 0*0=0 → sum=1
        # Test: user_3: 1*0=0, user_4: 0*1=0 → sum=0
        assert control.main_covariate_sum_product is not None
        self.assertEqual(control.main_covariate_sum_product, 1)
        self.assertEqual(test_variant.main_covariate_sum_product, 0)
