import os
import random
import tempfile
import unittest

import numpy as np
import pandas as pd
from sam.models import ConstantTimeseriesRegressor
from sam.models.constant_model import ConstantTemplate
from sklearn.utils.estimator_checks import check_estimator


class TestConstantTemplate(unittest.TestCase):
    def test_sklearn_estimator(self):
        """Test if default template follows sklearn estimator standards"""
        model = ConstantTemplate()
        check_estimator(model)


class TestConstantTimeseriesRegressor(unittest.TestCase):
    def setUp(self):
        """
        We are deliberately creating an extremely easy, linear problem here
        the target is literally 17 times one of the features
        This is because we just want to see if the model works at all, in a short time, on very
        little data.
        With a high enough learning rate, it should be almost perfect after a few iterations
        """

        self.n_rows = 100
        self.train_size = int(self.n_rows * 0.8)

        self.X = pd.DataFrame(
            {
                "TIME": pd.to_datetime(np.array(range(self.n_rows)), unit="m"),
                "x": range(self.n_rows),
            }
        )

        self.y = 17 * self.X["x"] + 34
        self.X_train, self.X_test = self.X[: self.train_size], self.X[self.train_size :]
        self.y_train, self.y_test = self.y[: self.train_size], self.y[self.train_size :]

        # Now start setting the RNG so we get reproducible results
        random.seed(42)
        np.random.seed(42)
        os.environ["PYTHONHASHSEED"] = "0"

    def test_default_params(self):
        """Sanity check if default params work
        Score should be 0, since this is a benchmark model
        """
        model = ConstantTimeseriesRegressor(timecol="TIME")
        model.fit(self.X_train, self.y_train)
        preds = model.predict(self.X_test, self.y_test)
        score = model.score(self.X_test, self.y_test)

        # Loss score should be equal to the MSE, since there are no quantiles
        exp_y = model.get_actual(self.y_test)
        exp_score = -(exp_y - preds).abs().mean().mean()
        self.assertEqual(score, exp_score)

    def test_normal_use(self):
        """Test if the SPC model performs normally with some quantiles"""
        model = ConstantTimeseriesRegressor(timecol="TIME", quantiles=(0.25, 0.75))
        model.fit(self.X_train, self.y_train)
        y_pred = model.predict(self.X_test, self.y_test)

        self.assertEqual(y_pred.shape, (20, 3))
        self.assertListEqual(list(y_pred.index), list(self.y_test.index))

    def test_replacement_sam(self):
        """Test if SPC model also works with all the default SAM parameters"""
        model = ConstantTimeseriesRegressor(
            predict_ahead=[1],
            quantiles=[],
            use_diff_of_y=True,
            timecol="TIME",
            y_scaler=None,
        )
        model.fit(self.X_train, self.y_train)
        y_pred = model.predict(self.X_test, self.y_test)

        self.assertEqual(y_pred.shape, (20,))
        self.assertListEqual(list(y_pred.index), list(self.y_test.index))

    def test_dump_load(self):
        """Test if the model can be dumped and loaded"""
        temp_dir = tempfile.gettempdir()

        model = ConstantTimeseriesRegressor(timecol="TIME", quantiles=(0.25, 0.75))
        model.fit(self.X_train, self.y_train)
        model.dump(temp_dir)

        del model

        new_model = ConstantTimeseriesRegressor.load(foldername=temp_dir)
        y_pred = new_model.predict(self.X_test, self.y_test)

        self.assertEqual(y_pred.shape, (20, 3))
        self.assertListEqual(list(y_pred.index), list(self.y_test.index))


if __name__ == "__main__":
    unittest.main()
