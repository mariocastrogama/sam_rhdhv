import unittest
from pandas.testing import assert_series_equal, assert_frame_equal
from numpy.testing import assert_array_equal
from sam.feature_engineering import BuildRollingFeatures, fourier
import pandas as pd
import numpy as np


class TestRollingFeatures(unittest.TestCase):

    def setUp(self):
        self.X = pd.DataFrame({
            "X": [10, 12, 15, 9, 0, 0, 1]
        })

        def simple_transform(rolling_type, lookback, window_size):
            roller = BuildRollingFeatures(rolling_type, lookback, window_size=window_size,
                                          keep_original=False)
            return roller.fit_transform(self.X)
        self.simple_transform = simple_transform

    def test_lag(self):
        result = self.simple_transform('lag', 0, [0, 1, 2, 3])
        expected = pd.DataFrame({
            "X_lag_0": (10, 12, 15, 9, 0, 0, 1),
            "X_lag_1": (np.nan, 10, 12, 15, 9, 0, 0),
            "X_lag_2": (np.nan, np.nan, 10, 12, 15, 9, 0),
            "X_lag_3": (np.nan, np.nan, np.nan, 10, 12, 15, 9)
        }, columns=["X_lag_0", "X_lag_1", "X_lag_2", "X_lag_3"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_sum(self):
        result = self.simple_transform('sum', 0, [1, 2, 3])
        expected = pd.DataFrame({
            "X_sum_1": [10, 12, 15, 9, 0, 0, 1],
            "X_sum_2": [np.nan, 22, 27, 24, 9, 0, 1],
            "X_sum_3": [np.nan, np.nan, 37, 36, 24, 9, 1]
        }, columns=["X_sum_1", "X_sum_2", "X_sum_3"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_mean(self):
        result = self.simple_transform('mean', 0, [1, 2, 3])
        expected = pd.DataFrame({
            "X_mean_1": [10, 12, 15, 9, 0, 0, 1],
            "X_mean_2": [np.nan, 11, 13.5, 12, 4.5, 0, 0.5],
            "X_mean_3": [np.nan, np.nan, 12 + 1/3, 12, 8, 3, 1/3]
        }, columns=["X_mean_1", "X_mean_2", "X_mean_3"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_window_zero(self):
        result = self.simple_transform('lag', 1, [0, 1, 2])
        expected = pd.DataFrame({
            "X_lag_0": (np.nan, 10, 12, 15, 9, 0, 0),
            "X_lag_1": (np.nan, np.nan, 10, 12, 15, 9, 0),
            "X_lag_2": (np.nan, np.nan, np.nan, 10, 12, 15, 9)
        }, columns=["X_lag_0", "X_lag_1", "X_lag_2"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_useless_feature(self):
        # useless because no lag, it's just identity function
        result = self.simple_transform('lag', 0, 0)
        expected = pd.DataFrame({
            "X_lag_0": (10, 12, 15, 9, 0, 0, 1)
        }, columns=["X_lag_0"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_diff(self):
        result = self.simple_transform('diff', 0, [1, 2, 3])
        expected = pd.DataFrame({
            "X_diff_1": [np.nan, 2, 3, -6, -9, 0, 1],
            "X_diff_2": [np.nan, np.nan, 5, -3, -15, -9, 1],
            "X_diff_3": [np.nan, np.nan, np.nan, -1, -12, -15, -8]
        }, columns=["X_diff_1", "X_diff_2", "X_diff_3"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_numpos(self):
        result = self.simple_transform('numpos', 0, [1, 2, 3])
        expected = pd.DataFrame({
            "X_numpos_1": [1, 1, 1, 1, 0, 0, 1],
            "X_numpos_2": [np.nan, 2, 2, 2, 1, 0, 1],
            "X_numpos_3": [np.nan, np.nan, 3, 3, 2, 1, 1]
        }, columns=["X_numpos_1", "X_numpos_2", "X_numpos_3"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_fourier(self):
        # Helper function to calculate a single row of fft values
        def fastfft(values):
            return np.absolute(np.fft.fft(np.array(values)))[1:3]

        expected = [np.array([np.nan, np.nan]),
                    np.array([np.nan, np.nan]),
                    np.array([np.nan, np.nan]),
                    fastfft(self.X.X.iloc[0:4]),
                    fastfft(self.X.X.iloc[1:5]),
                    fastfft(self.X.X.iloc[2:6]),
                    fastfft(self.X.X.iloc[3:7])]
        expected = pd.DataFrame(expected,
                                columns=["X_fourier_4_1", "X_fourier_4_2"])
        result = self.simple_transform('fourier', 0, 4)
        assert_frame_equal(result, expected)

    # all the others are not tested because they are functionally exactly identical.
    # for example: std is just  lambda arr, n: arr.rolling(n).std(), which is just
    # exactly the same as sum or mean

    # Only two tests for lookback needed, because they are all treated in the exact same way
    # only fourier is treated differently.
    def test_lookback_normal(self):

        result = self.simple_transform('lag', 2, [1, 2, 3])
        expected = pd.DataFrame({
            "X_lag_1": (np.nan, np.nan, np.nan, 10, 12, 15, 9),
            "X_lag_2": (np.nan, np.nan, np.nan, np.nan, 10, 12, 15),
            "X_lag_3": (np.nan, np.nan, np.nan, np.nan, np.nan, 10, 12)
        }, columns=["X_lag_1", "X_lag_2", "X_lag_3"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_lookback_fourier(self):
        # Helper function to calculate a single row of fft values
        def fastfft(values):
            return np.absolute(np.fft.fft(np.array(values)))[1:3]

        expected = [np.array([np.nan, np.nan]),
                    np.array([np.nan, np.nan]),
                    np.array([np.nan, np.nan]),
                    np.array([np.nan, np.nan]),
                    fastfft(self.X.X.iloc[0:4]),
                    fastfft(self.X.X.iloc[1:5]),
                    fastfft(self.X.X.iloc[2:6])]
        expected = pd.DataFrame(expected,
                                columns=["X_fourier_4_1", "X_fourier_4_2"])
        result = self.simple_transform('fourier', 1, 4)
        assert_frame_equal(result, expected)

    # keep_original is always treated the exact same, so only one test needed
    def test_keep_original(self):
        roller = BuildRollingFeatures(rolling_type='lag', lookback=0, window_size=[1, 2, 3],
                                      keep_original=True)
        result = roller.fit_transform(self.X)
        expected = pd.DataFrame({
            "X": self.X.X,
            "X_lag_1": (np.nan, 10, 12, 15, 9, 0, 0),
            "X_lag_2": (np.nan, np.nan, 10, 12, 15, 9, 0),
            "X_lag_3": (np.nan, np.nan, np.nan, 10, 12, 15, 9)
        }, columns=["X", "X_lag_1", "X_lag_2", "X_lag_3"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_calc_window_size(self):
        roller = BuildRollingFeatures(rolling_type='lag', lookback=0, freq='30 minuutjes',
                                      keep_original=False, values_roll=[1, 2, 3], unit_roll='hour')
        result = roller.fit_transform(self.X)
        expected = pd.DataFrame({
            "X_lag_1_hour": (np.nan, np.nan, 10, 12, 15, 9, 0),
            "X_lag_2_hour": (np.nan, np.nan, np.nan, np.nan, 10, 12, 15),
            "X_lag_3_hour": (np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, 10)
        }, columns=["X_lag_1_hour", "X_lag_2_hour", "X_lag_3_hour"])
        assert_frame_equal(result, expected, check_dtype=False)

    def test_get_feature_names(self):
        roller = BuildRollingFeatures('lag', lookback=0, window_size=[1, 2, 3])
        _ = roller.fit_transform(self.X)
        result = roller.get_feature_names()
        expected = ['X', 'X_lag_1', 'X_lag_2', 'X_lag_3']
        self.assertEqual(result, expected)

    def test_incorrect_inputs(self):
        # helper function. This function should already throw exceptions if the input is incorrect
        def validate(X=self.X, **kwargs):
            roller = BuildRollingFeatures(**kwargs)
            roller.fit_transform(X)
        self.assertRaises(Exception, validate)  # No input
        self.assertRaises(ValueError, validate, lookback=-1, window_size=1)  # negative lookback
        self.assertRaises(TypeError, validate, window_size="INVALID")  # typeerror
        self.assertRaises(Exception, validate, window_size=[1, 2, None])  # runtime error
        # values_roll cannot be string
        self.assertRaises(TypeError, validate, freq='15min', values_roll='30', unit_roll='minutes')
        # unit_roll must be a string
        self.assertRaises(TypeError, validate, freq='15min', values_roll=30, unit_roll=1)
        # freq must be a string
        self.assertRaises(TypeError, validate, freq=1, values_roll=30, unit_roll='minutes')
        self.assertRaises(Exception, validate, freq='45min', values_roll=[1, 2, 3],
                          unit_roll='hour')  # does not divide
        # must be pandas
        self.assertRaises(Exception, validate, X=np.array([[1, 2, 3], [2, 3, 4]]), window_size=1)
        self.assertRaises(TypeError, validate, window_size=1, keep_original="yes please")
        self.assertRaises(TypeError, validate, window_size=1, rolling_type=np.mean)
        self.assertRaises(TypeError, validate, window_size=1, lookback="2")

if __name__ == '__main__':
    unittest.main()