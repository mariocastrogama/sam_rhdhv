import unittest
import warnings

import numpy as np
from numpy.testing import assert_array_almost_equal
from sam.metrics import train_r2, train_mean_r2

PARAM_LIST = [np.nanmean, np.nanmedian]


class TestTrainR2(unittest.TestCase):
    def test_train_r2(self):
        from sam.metrics import train_r2
        from sklearn.metrics import r2_score

        for train_avg_func in PARAM_LIST:
            with self.subTest():
                np.random.seed(42)
                N = 1000
                model = np.zeros(N)
                for f in [0.001, 0.005, 0.01, 0.05]:
                    for p in [0, np.pi/4]:
                        model += (1/f) * np.sin(2*np.pi*f*np.arange(N) + p)
                data = model + np.random.normal(scale=250, size=N)

                custom_r2s = []
                keras_r2s = []
                for test_ratio in [0.8, 0.5, 0.2]:

                    test_n = int(test_ratio * N)
                    train_n = N-test_n
                    train_data = data[:train_n]
                    test_data = data[train_n:]
                    # train_pred = model[:train_n]
                    test_pred = model[train_n:]

                    keras_r2s.append(r2_score(test_data, test_pred))
                    custom_r2s.append(train_r2(test_data, test_pred, train_avg_func(train_data)))

                # keras r2 should decrease with decreasing test size, custom r2 should do so less
                assert_array_almost_equal(keras_r2s, [0.962522, 0.894608, 0.734713])
                if train_avg_func == np.nanmean:
                    assert_array_almost_equal(custom_r2s, [0.987602, 0.989454, 0.870157])
                elif train_avg_func == np.nanmedian:
                    assert_array_almost_equal(custom_r2s, [0.987653, 0.990700, 0.938786])

    def test_train_r2_shapes(self):
        # the function cannot handle data with multiple dimensions. It does however ravel
        # empty dimensions (x, 1).
        self.assertRaises(AssertionError, train_r2, np.random.random(
            size=(12, 2)), np.random.random(size=(12, 2)), 0)
        self.assertRaises(AssertionError, train_r2, np.random.random(
            size=(12, 1)), np.random.random(size=(12, 2)), 0)
        self.assertRaises(AssertionError, train_r2, np.random.random(
            size=(12, 2)), np.random.random(size=(12, 1)), 0)

    def test_train_mean_r2_deprecation_warning(self):
        with warnings.catch_warnings(record=True) as w:
            # Cause all warnings to always be triggered
            warnings.simplefilter("always")

            # Prepare parameters
            true_array = np.array([0, 1, 2, 3, 4])
            predicted_array = np.array([1, 2, 3, 4, 5])

            # Trigger a warning
            r2 = train_mean_r2(true_array, predicted_array, np.nanmedian(true_array))

            # Verify some things
            assert r2 == 0.5
            assert len(w) == 1
            assert issubclass(w[-1].category, DeprecationWarning)
            assert "DEPRECATED" in str(w[-1].message)


if __name__ == '__main__':
    unittest.main()
