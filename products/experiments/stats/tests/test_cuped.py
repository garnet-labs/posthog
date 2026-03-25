from unittest import TestCase

import numpy as np
from parameterized import parameterized

from products.experiments.stats.bayesian.method import BayesianConfig, BayesianMethod
from products.experiments.stats.frequentist.method import FrequentistConfig, FrequentistMethod
from products.experiments.stats.shared.cuped import CupedData, compute_theta, cuped_adjust
from products.experiments.stats.shared.enums import DifferenceType
from products.experiments.stats.shared.statistics import (
    ProportionStatistic,
    RatioStatistic,
    SampleMeanStatistic,
    StatisticError,
)


def _generate_sufficient_stats(rng: np.random.Generator, n: int, mean: float, std: float):
    """Generate sufficient statistics (sum, sum_squares) from synthetic data."""
    data = rng.normal(mean, std, n)
    return float(np.sum(data)), float(np.sum(data**2)), data


class TestComputeTheta(TestCase):
    def test_theta_with_known_correlation(self):
        """When Y = 2X + noise, theta should be approximately 2."""
        rng = np.random.default_rng(42)
        n_t, n_c = 1000, 1000

        # Generate pre-exposure data
        pre_t = rng.normal(10, 3, n_t)
        pre_c = rng.normal(10, 3, n_c)

        # Post = 2 * Pre + noise
        post_t = 2 * pre_t + rng.normal(0, 1, n_t)
        post_c = 2 * pre_c + rng.normal(0, 1, n_c)

        treatment_post = SampleMeanStatistic(n=n_t, sum=float(np.sum(post_t)), sum_squares=float(np.sum(post_t**2)))
        control_post = SampleMeanStatistic(n=n_c, sum=float(np.sum(post_c)), sum_squares=float(np.sum(post_c**2)))
        treatment_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n_t, sum=float(np.sum(pre_t)), sum_squares=float(np.sum(pre_t**2))),
            sum_of_cross_products=float(np.sum(post_t * pre_t)),
        )
        control_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n_c, sum=float(np.sum(pre_c)), sum_squares=float(np.sum(pre_c**2))),
            sum_of_cross_products=float(np.sum(post_c * pre_c)),
        )

        theta = compute_theta(treatment_post, control_post, treatment_cuped, control_cuped)
        self.assertAlmostEqual(theta, 2.0, places=1)

    def test_theta_zero_when_no_pre_variance(self):
        """When all pre-exposure values are identical, theta should be 0."""
        n = 100
        treatment_post = SampleMeanStatistic(n=n, sum=500.0, sum_squares=3000.0)
        control_post = SampleMeanStatistic(n=n, sum=480.0, sum_squares=2800.0)

        # Constant pre-exposure values: all 5.0
        constant_pre = SampleMeanStatistic(n=n, sum=500.0, sum_squares=2500.0)
        treatment_cuped = CupedData(pre_statistic=constant_pre, sum_of_cross_products=2500.0)
        control_cuped = CupedData(pre_statistic=constant_pre, sum_of_cross_products=2400.0)

        theta = compute_theta(treatment_post, control_post, treatment_cuped, control_cuped)
        self.assertEqual(theta, 0.0)

    def test_theta_with_uncorrelated_data(self):
        """When pre and post are independent, theta should be near 0."""
        rng = np.random.default_rng(123)
        n = 5000

        pre = rng.normal(10, 3, n)
        post = rng.normal(20, 5, n)

        treatment_post = SampleMeanStatistic(n=n, sum=float(np.sum(post)), sum_squares=float(np.sum(post**2)))
        treatment_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre)), sum_squares=float(np.sum(pre**2))),
            sum_of_cross_products=float(np.sum(post * pre)),
        )

        # Use same data for control to isolate theta behavior
        theta = compute_theta(treatment_post, treatment_post, treatment_cuped, treatment_cuped)
        self.assertAlmostEqual(theta, 0.0, places=0)


class TestCupedAdjust(TestCase):
    def test_variance_reduction_with_correlated_data(self):
        """CUPED should reduce variance when pre and post are correlated."""
        rng = np.random.default_rng(42)
        n_t, n_c = 1000, 1000

        pre_t = rng.normal(10, 3, n_t)
        pre_c = rng.normal(10, 3, n_c)
        post_t = 2 * pre_t + rng.normal(0.5, 1, n_t)  # treatment has +0.5 effect
        post_c = 2 * pre_c + rng.normal(0, 1, n_c)

        treatment_post = SampleMeanStatistic(n=n_t, sum=float(np.sum(post_t)), sum_squares=float(np.sum(post_t**2)))
        control_post = SampleMeanStatistic(n=n_c, sum=float(np.sum(post_c)), sum_squares=float(np.sum(post_c**2)))
        treatment_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n_t, sum=float(np.sum(pre_t)), sum_squares=float(np.sum(pre_t**2))),
            sum_of_cross_products=float(np.sum(post_t * pre_t)),
        )
        control_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n_c, sum=float(np.sum(pre_c)), sum_squares=float(np.sum(pre_c**2))),
            sum_of_cross_products=float(np.sum(post_c * pre_c)),
        )

        result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)

        # Variance should be significantly reduced
        self.assertGreater(result.variance_reduction_treatment, 0.5)
        self.assertGreater(result.variance_reduction_control, 0.5)

        # Adjusted stats should have lower variance than originals
        self.assertLess(result.treatment_adjusted.variance, treatment_post.variance)
        self.assertLess(result.control_adjusted.variance, control_post.variance)

        # Theta should be approximately 2
        self.assertAlmostEqual(result.theta, 2.0, places=1)

    def test_unadjusted_means_preserved(self):
        """CupedResult should contain the original unadjusted means."""
        rng = np.random.default_rng(42)
        n = 500

        pre = rng.normal(10, 3, n)
        post_t = pre + rng.normal(1, 1, n)
        post_c = pre + rng.normal(0, 1, n)

        treatment_post = SampleMeanStatistic(n=n, sum=float(np.sum(post_t)), sum_squares=float(np.sum(post_t**2)))
        control_post = SampleMeanStatistic(n=n, sum=float(np.sum(post_c)), sum_squares=float(np.sum(post_c**2)))
        treatment_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre)), sum_squares=float(np.sum(pre**2))),
            sum_of_cross_products=float(np.sum(post_t * pre)),
        )
        control_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre)), sum_squares=float(np.sum(pre**2))),
            sum_of_cross_products=float(np.sum(post_c * pre)),
        )

        result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)

        self.assertAlmostEqual(result.treatment_unadjusted_mean, treatment_post.mean, places=10)
        self.assertAlmostEqual(result.control_unadjusted_mean, control_post.mean, places=10)

    def test_no_adjustment_when_zero_pre_variance(self):
        """When pre-exposure has zero variance, should return original stats with theta=0."""
        n = 100
        treatment_post = SampleMeanStatistic(n=n, sum=500.0, sum_squares=3000.0)
        control_post = SampleMeanStatistic(n=n, sum=480.0, sum_squares=2800.0)

        constant_pre = SampleMeanStatistic(n=n, sum=500.0, sum_squares=2500.0)
        treatment_cuped = CupedData(pre_statistic=constant_pre, sum_of_cross_products=2500.0)
        control_cuped = CupedData(pre_statistic=constant_pre, sum_of_cross_products=2400.0)

        result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)

        self.assertEqual(result.theta, 0.0)
        self.assertEqual(result.variance_reduction_treatment, 0.0)
        self.assertEqual(result.variance_reduction_control, 0.0)
        self.assertAlmostEqual(result.treatment_adjusted.mean, treatment_post.mean, places=10)
        self.assertAlmostEqual(result.control_adjusted.mean, control_post.mean, places=10)

    def test_proportion_input_produces_sample_mean_output(self):
        """ProportionStatistic inputs should produce SampleMeanStatistic outputs."""
        n = 1000
        treatment_post = ProportionStatistic(n=n, sum=150)
        control_post = ProportionStatistic(n=n, sum=120)

        rng = np.random.default_rng(42)
        pre_t = rng.normal(0.15, 0.05, n)
        pre_c = rng.normal(0.12, 0.05, n)

        # Generate correlated cross products
        treatment_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre_t)), sum_squares=float(np.sum(pre_t**2))),
            sum_of_cross_products=float(np.sum(rng.binomial(1, 0.15, n) * pre_t)),
        )
        control_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre_c)), sum_squares=float(np.sum(pre_c**2))),
            sum_of_cross_products=float(np.sum(rng.binomial(1, 0.12, n) * pre_c)),
        )

        result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)

        self.assertIsInstance(result.treatment_adjusted, SampleMeanStatistic)
        self.assertIsInstance(result.control_adjusted, SampleMeanStatistic)

    @parameterized.expand(
        [
            ("high_correlation", 0.95, 0.8),
            ("medium_correlation", 0.5, 0.05),
        ]
    )
    def test_variance_reduction_scales_with_correlation(self, _name, correlation, min_reduction):
        """Higher correlation between pre and post should give more variance reduction."""
        rng = np.random.default_rng(42)
        n = 2000

        pre = rng.normal(10, 3, n)
        noise_std = 3 * np.sqrt(1 - correlation**2) / correlation if correlation > 0 else 100
        post = correlation * (3 / 3) * pre + rng.normal(0, noise_std, n)

        stat_post = SampleMeanStatistic(n=n, sum=float(np.sum(post)), sum_squares=float(np.sum(post**2)))
        cuped_data = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre)), sum_squares=float(np.sum(pre**2))),
            sum_of_cross_products=float(np.sum(post * pre)),
        )

        result = cuped_adjust(stat_post, stat_post, cuped_data, cuped_data)
        self.assertGreater(result.variance_reduction_treatment, min_reduction)


class TestCupedEdgeCases(TestCase):
    def test_mismatched_n_raises_error(self):
        treatment_post = SampleMeanStatistic(n=100, sum=500.0, sum_squares=3000.0)
        control_post = SampleMeanStatistic(n=100, sum=480.0, sum_squares=2800.0)

        treatment_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=99, sum=490.0, sum_squares=2500.0),  # wrong n
            sum_of_cross_products=2450.0,
        )
        control_cuped = CupedData(
            pre_statistic=SampleMeanStatistic(n=100, sum=480.0, sum_squares=2400.0),
            sum_of_cross_products=2300.0,
        )

        with self.assertRaises(StatisticError, msg="Treatment post n"):
            cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)

    def test_mismatched_types_raises_error(self):
        treatment_post = SampleMeanStatistic(n=100, sum=500.0, sum_squares=3000.0)
        control_post = ProportionStatistic(n=100, sum=50)

        cuped_data = CupedData(
            pre_statistic=SampleMeanStatistic(n=100, sum=480.0, sum_squares=2400.0),
            sum_of_cross_products=2300.0,
        )

        with self.assertRaises(StatisticError, msg="same type"):
            cuped_adjust(treatment_post, control_post, cuped_data, cuped_data)

    def test_ratio_statistic_raises_error(self):
        n = 100
        m_stat = SampleMeanStatistic(n=n, sum=500.0, sum_squares=3000.0)
        d_stat = SampleMeanStatistic(n=n, sum=100.0, sum_squares=200.0)
        treatment_post = RatioStatistic(n=n, m_statistic=m_stat, d_statistic=d_stat, m_d_sum_of_products=600.0)
        control_post = RatioStatistic(n=n, m_statistic=m_stat, d_statistic=d_stat, m_d_sum_of_products=600.0)

        cuped_data = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=480.0, sum_squares=2400.0),
            sum_of_cross_products=2300.0,
        )

        with self.assertRaises(StatisticError, msg="ratio metrics"):
            cuped_adjust(treatment_post, control_post, cuped_data, cuped_data)

    def test_small_sample_size(self):
        """CUPED should work (without crashing) even with small samples."""
        n = 5
        rng = np.random.default_rng(42)
        pre = rng.normal(10, 3, n)
        post = pre + rng.normal(1, 1, n)

        stat_post = SampleMeanStatistic(n=n, sum=float(np.sum(post)), sum_squares=float(np.sum(post**2)))
        cuped_data = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre)), sum_squares=float(np.sum(pre**2))),
            sum_of_cross_products=float(np.sum(post * pre)),
        )

        result = cuped_adjust(stat_post, stat_post, cuped_data, cuped_data)
        self.assertIsNotNone(result.theta)
        self.assertIsInstance(result.treatment_adjusted, SampleMeanStatistic)


class TestCupedIntegration(TestCase):
    """End-to-end tests: CUPED adjust → statistical test."""

    def _make_correlated_data(self, rng, n, pre_mean, effect, noise_std):
        pre = rng.normal(pre_mean, 3, n)
        post = pre + rng.normal(effect, noise_std, n)
        post_stat = SampleMeanStatistic(n=n, sum=float(np.sum(post)), sum_squares=float(np.sum(post**2)))
        cuped_data = CupedData(
            pre_statistic=SampleMeanStatistic(n=n, sum=float(np.sum(pre)), sum_squares=float(np.sum(pre**2))),
            sum_of_cross_products=float(np.sum(post * pre)),
        )
        return post_stat, cuped_data

    def test_frequentist_cuped_narrows_confidence_interval(self):
        """CUPED-adjusted stats should produce tighter CIs than unadjusted."""
        rng = np.random.default_rng(42)

        treatment_post, treatment_cuped = self._make_correlated_data(rng, 1000, 10, 0.5, 1)
        control_post, control_cuped = self._make_correlated_data(rng, 1000, 10, 0, 1)

        # Unadjusted
        method = FrequentistMethod(FrequentistConfig(difference_type=DifferenceType.ABSOLUTE))
        unadjusted_result = method.run_test(treatment_post, control_post)

        # CUPED-adjusted
        cuped_result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)
        adjusted_result = method.run_test(cuped_result.treatment_adjusted, cuped_result.control_adjusted)

        unadjusted_width = unadjusted_result.confidence_interval[1] - unadjusted_result.confidence_interval[0]
        adjusted_width = adjusted_result.confidence_interval[1] - adjusted_result.confidence_interval[0]

        self.assertLess(adjusted_width, unadjusted_width)

    def test_bayesian_cuped_narrows_credible_interval(self):
        """CUPED-adjusted stats should produce tighter credible intervals than unadjusted."""
        rng = np.random.default_rng(42)

        treatment_post, treatment_cuped = self._make_correlated_data(rng, 1000, 10, 0.5, 1)
        control_post, control_cuped = self._make_correlated_data(rng, 1000, 10, 0, 1)

        method = BayesianMethod(BayesianConfig(difference_type=DifferenceType.ABSOLUTE))

        # Unadjusted
        unadjusted_result = method.run_test(treatment_post, control_post)

        # CUPED-adjusted
        cuped_result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)
        adjusted_result = method.run_test(cuped_result.treatment_adjusted, cuped_result.control_adjusted)

        unadjusted_width = unadjusted_result.credible_interval[1] - unadjusted_result.credible_interval[0]
        adjusted_width = adjusted_result.credible_interval[1] - adjusted_result.credible_interval[0]

        self.assertLess(adjusted_width, unadjusted_width)

    def test_frequentist_cuped_produces_valid_result(self):
        """CUPED-adjusted results should be structurally valid."""
        rng = np.random.default_rng(42)

        treatment_post, treatment_cuped = self._make_correlated_data(rng, 500, 10, 1, 2)
        control_post, control_cuped = self._make_correlated_data(rng, 500, 10, 0, 2)

        cuped_result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)

        method = FrequentistMethod(FrequentistConfig(difference_type=DifferenceType.ABSOLUTE))
        result = method.run_test(cuped_result.treatment_adjusted, cuped_result.control_adjusted)

        self.assertIsNotNone(result.p_value)
        self.assertGreaterEqual(result.p_value, 0)
        self.assertLessEqual(result.p_value, 1)
        self.assertLess(result.confidence_interval[0], result.confidence_interval[1])

    def test_bayesian_cuped_produces_valid_result(self):
        """CUPED-adjusted results should be structurally valid for Bayesian method."""
        rng = np.random.default_rng(42)

        treatment_post, treatment_cuped = self._make_correlated_data(rng, 500, 10, 1, 2)
        control_post, control_cuped = self._make_correlated_data(rng, 500, 10, 0, 2)

        cuped_result = cuped_adjust(treatment_post, control_post, treatment_cuped, control_cuped)

        method = BayesianMethod(BayesianConfig(difference_type=DifferenceType.ABSOLUTE))
        result = method.run_test(cuped_result.treatment_adjusted, cuped_result.control_adjusted)

        self.assertIsNotNone(result.chance_to_win)
        self.assertGreaterEqual(result.chance_to_win, 0)
        self.assertLessEqual(result.chance_to_win, 1)
        self.assertLess(result.credible_interval[0], result.credible_interval[1])
