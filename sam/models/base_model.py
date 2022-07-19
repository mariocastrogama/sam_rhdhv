from os import remove
import warnings
from abc import ABC, abstractmethod
from operator import itemgetter
from typing import Callable, Sequence, Tuple, Union, List

import numpy as np
import pandas as pd
from sam.feature_engineering import IdentityFeatureEngineer
from sam.preprocessing import inverse_differenced_target, make_shifted_target
from sam.feature_engineering import BaseFeatureEngineer
from sam.utils import assert_contains_nans, make_df_monotonic
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from sklearn.utils.validation import check_is_fitted
from sam.models.utils import remove_target_nan, remove_until_first_value


class BaseTimeseriesRegressor(BaseEstimator, RegressorMixin, ABC):
    """
    This is an abstract class for all SAM models.
    Every SAM model (including the most used SamQuantileMLP)
    needs to inherit this class and implement the abstract methods.

    There are some notes:
    - There is no validation yet. Therefore, the input data must already be sorted and monospaced
    - The feature engineering should be provided as a any transformer. If the feature engineering
      is not provided, the identity transformer will be used. Good practice is for example to use
      the SimpleFeatureEngineer
    - The prediction requires y as input. The reason for this is described in the predict function.
      Keep in mind that this is not directly 'cheating', since we are predicting a future value of
      y, and giving the present value of y as input to the predict.
      When predicting the present, this y is not needed and can be None

    Note that the below parameters are just for the abstract base class, and subclasses can have
    different `__init__` parameters.

    Parameters
    ----------
    predict_ahead: integer or list of integers, optional (default=1)
        how many steps to predict ahead. For example, if [1, 2], the model will predict both 1 and
        2 timesteps into the future. If [0], predict the present. If not equal to 0 or [0],
        predict the future, with differencing.
        A single integer is also allowed, in which case the value is converted to a singleton list.
    quantiles: array-like, optional (default=())
        The quantiles to predict. Between 0 and 1. Keep in mind that the mean will be predicted
        regardless of this parameter
    use_diff_of_y: bool, optional (default=True)
        If True differencing is used (the difference between y now and shifted y),
        else differencing is not used (shifted y is used).
    timecol: string, optional (default=None)
        If not None, the column to use for constructing time features. For now,
        creating features from a DateTimeIndex is not supported yet.
    y_scaler: object, optional (default=None)
        Should be an sklearn-type transformer that has a transform and inverse_transform method.
        E.g.: StandardScaler() or PowerTransformer()

    Attributes
    ----------
    feature_engineer_: Sklearn transformer
        The transformer used on the raw data before prediction
    prediction_cols_: array of strings
        The names of the output columns from the model.
    model_: underlying model (not implemented here)
        The underlying model
    """

    def __init__(
        self,
        predict_ahead: Union[int, List[int]] = 1,
        quantiles: Sequence[float] = (),
        use_diff_of_y: bool = True,
        timecol: str = None,
        y_scaler: TransformerMixin = None,
        feature_engineer: BaseFeatureEngineer = None,
    ) -> None:
        self.predict_ahead = predict_ahead if isinstance(predict_ahead, List) else [predict_ahead]
        self.quantiles = quantiles
        self.use_diff_of_y = use_diff_of_y
        self.timecol = timecol
        self.y_scaler = y_scaler
        self.feature_engineer_ = feature_engineer if feature_engineer else IdentityFeatureEngineer

    @abstractmethod
    def get_untrained_model(self) -> Callable:
        """Returns an underlying model that can be trained

        This abstract method needs to be implemented by any class that inherits from
        SamQuantileRegressor. It returns a trainable model like Sklearn, keras or
        anything you can think of

        Returns
        -------
        A trainable model class
        """
        return NotImplemented

    def validate_predict_ahead(self):
        """
        Perform checks to validate the predict_ahead attribute
        """
        if np.isscalar(self.predict_ahead):
            self.predict_ahead = [self.predict_ahead]

        if not all([p >= 0 for p in self.predict_ahead]):
            raise ValueError("All values of predict_ahead must be 0 or larger!")

        if self.predict_ahead == [0] and self.use_diff_of_y:
            raise ValueError("use_diff_of_y must be false when predict_ahead is 0")

        # TODO: Make sure this is correct
        # if self.predict_ahead == [0] and self.use_y_as_feature:
        #     raise ValueError("use_y_as_feature must be false when predict_ahead is 0")

        if len(np.unique(self.predict_ahead)) != len(self.predict_ahead):
            raise ValueError("predict_ahead contains double values")

    def validate_data(self, X: pd.DataFrame) -> None:
        """
        Validates the data and raises an exception if:
        - There is no time columns
        - The data is not monospaced
        - There is not enought data

        Parameters
        ----------
        x: pd.DataFrame
            The dataframe to validate
        """
        if self.timecol is None:
            pass
            # TODO: Support for DateTimeIndex
            # warnings.warn(
            #     (
            #         "No timecolumn given. Make sure the data is"
            #         "monospaced when given to this model!"
            #     ),
            #     UserWarning,
            # )
        else:
            monospaced = X[self.timecol].diff()[1:].unique().size == 1
            if not monospaced:
                raise ValueError(
                    "Data is not monospaced, which is required for"
                    "this model. fit/predict is not possible"
                )

        # TODO: Add this check somewhere
        # enough_data = len(self.rolling_window_size) == 0 or X.shape[0] > max(
        #     self.rolling_window_size
        # )
        # if not enough_data:
        #     warnings.warn(
        #         "Not enough data given to calculate rolling features. "
        #         "Output will be entirely missing values.",
        #         UserWarning,
        #     )

    @staticmethod
    def verify_same_indexes(X: pd.DataFrame, y: pd.Series, y_can_be_none=True):
        """
        Verify that X and y have the same index
        """
        if not y.index.equals(X.index):
            raise ValueError("For training, X and y must have an identical index")

    def preprocess(self, X, y, train=False):
        """
        Preprocess the data. This is the first step in the pipeline.
        """
        X, y = X.copy(), y.copy()
        y = make_shifted_target(y, self.use_diff_of_y, self.predict_ahead)
        if train:
            if self.y_scaler is not None:
                y = pd.DataFrame(
                    self.y_scaler.fit_transform(y),
                    index=y.index,
                    columns=y.columns,
                )
            self._set_input_cols(X)
            X = pd.DataFrame(
                self.feature_engineer_.fit_transform(X, y),
                index=X.index,
                columns=self.get_feature_names(),
            )
            self.n_inputs_ = len(self.get_feature_names())
        else:
            if self.y_scaler is not None:
                y = pd.DataFrame(
                    self.y_scaler.transform(y),
                    index=y.index,
                    columns=y.columns,
                )
            X = pd.DataFrame(
                self.feature_engineer_.transform(X),
                index=X.index,
                columns=self.get_feature_names(),
            )

        return X, y

    def preprocess_fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        validation_data: Tuple[pd.DataFrame, pd.Series] = None,
    ) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
        """
        This function does the following:
        - Validate that the input is monospaced and has enough rows
        - Perform differencing on the target
        - Fitting/applying the feature engineer
        - Bookkeeping to create the output columns
        - Remove rows with nan that can't be used for fitting
        - Optionally, preprocess validation data to give to the fit

        Parameters
        ----------
        X: pd.DataFrame
            The independent variables used to 'train' the model
        y: pd.Series
            Target data (dependent variable) used to 'train' the model.
        validation_data: tuple(pd.DataFrame, pd.Series) (X_val, y_val respectively)
            Data used for validation step

        Returns
        -------
        X_trans: pd.DataDrame
            The transformed featuretable, ready to be used in fitting the model
        y_trans: pd.Series
            The transformed target, ready to be used in fitting the model
        X_val_trans: pd.DataFrame
            The transformed featuretable, ready to be used for validating the model
            If no validation data is provided, this returns None
        y_val_tranformed: pd.Series
            The transformed target, ready to be used for validating the model
            If no validation data is provided, this returns None
        """
        BaseTimeseriesRegressor.verify_same_indexes(X, y)
        self.validate_predict_ahead()
        self.validate_data(X)

        # Create output column names. In this model, our outputs are assumed to have the
        # form: [quantile_1_output_1, quantile_1_output_2, ... ,
        # quantile_n_output_1, quantile_n_output_2, ..., mean_output_1, mean_output_2]
        # Where n_output (1 or 2 in this example) is decided by self.predict_ahead
        self.prediction_cols_ = [
            "predict_lead_{}_q_{}".format(p, q) for q in self.quantiles for p in self.predict_ahead
        ]
        self.prediction_cols_ += ["predict_lead_{}_mean".format(p) for p in self.predict_ahead]
        self.n_outputs_ = len(self.prediction_cols_)

        X_trans, y_trans = self.preprocess(X, y, train=True)
        X_trans, y_trans = remove_until_first_value(X_trans, y_trans)
        X_trans, y_trans = remove_target_nan(X_trans, y_trans)
        assert_contains_nans(X_trans, "Data cannot contain nans. Imputation not supported for now")

        # Apply transformations to validation data if provided:
        if validation_data is not None:
            X_val, y_val = validation_data
            self.validate_data(X_val)
            X_val_trans, y_val_trans = self.preprocess(X_val, y_val, train=False)
            X_val_trans, y_val_trans = remove_until_first_value(X_val_trans, y_val_trans)
            X_val_trans, y_val_trans = remove_target_nan(X_val_trans, y_val_trans)
        else:
            X_val_trans, y_val_trans = (None, None)

        return X_trans, y_trans, X_val_trans, y_val_trans

    @abstractmethod
    def fit(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        validation_data: Tuple[pd.DataFrame, pd.Series] = None,
        **fit_kwargs,
    ) -> Callable:
        """Fit the underlying model

        This abstract method needs to be implemented by any class inheriting from
        SamQuantileRegressor. This function receives preprocessed input data and
        applies feature building and trains the underlying model.

        It is advised to use the `preprocess_fit()` function in any implementation.

        Parameters
        ----------
        X : pd.DataFrame
            The preprocessed input data for the model
        y : pd.Series
            The preprocessed target for the model
        validation_data : Tuple[pd.DataFrame, pd.Series], optional
            Validation data to calculate metric scores during training, by default None

        Returns
        -------
        Callable
            Usually this returns the history of the fit (when using keras)
        """
        return NotImplemented

    @abstractmethod
    def predict(
        self, X: pd.DataFrame, y: pd.Series = None, return_data: bool = False
    ) -> Union[pd.DataFrame, Tuple[pd.DataFrame, pd.DataFrame]]:
        """Predict on new data using a trained model

        This abstract method needs to be implemented by any class inheriting from
        SamQuantileRegressor. This function receives preprocessed input data and
        applies feature building and predicts the target using a trained model.

        Important! This is different from sklearn/tensorflow API...
        We need y during prediction for two reasons:
        1) a lagged version is used for feature engineering
        2) The underlying model can predict a differenced number, and then we want to output the
           'real' prediction, so we need y to undo the differencing
        Keep in mind that prediction will work if you are predicting the future. e.g. you have
        data from 00:00-12:00, and are predicting 4 hours into the future, it will predict what
        the value will be at 4:00-16:00

        It is advised to use the `preprocess_predict()` and
        `postprocess_predict()` functions in any implementation.

        Parameters
        ----------
        X : pd.DataFrame
            The independent variables used to predict.
        y : pd.Series, optional
            The target values, by default None
        return_data : bool, optional
            whether to return only the prediction, or to return both the prediction and the
            transformed input (X) dataframe., by default False

        Returns
        -------
        prediction: pd.DataFrame
            The predictions coming from the model
        X_trans: pd.DataFrame, optional
            The transformed input data, when return_data is True, otherwise None
        """
        return NotImplemented

    def preprocess_predict(
        self, X: pd.DataFrame, y: pd.Series, dropna: bool = False
    ) -> pd.DataFrame:
        """
        Transform a DataFrame X so it can be fed to self.model_.
        This is useful for several usecases, where you want to use the underlying
        keras model as opposed to the wrapper. For example shap, eli5, and even just
        implementing the `predict` function.

        Parameters
        ----------
        X: pd.DataFrame
            The training input samples.
        y: pd.Series
            The target values.
        dropna: bool, optional (default=False)
            If True, delete the rows that contain NaN values.
        """
        # This function only works if the estimator is fitted
        check_is_fitted(self, "feature_engineer_")

        if y is not None:
            BaseTimeseriesRegressor.verify_same_indexes(X, y)

        X_trans = pd.DataFrame(
            self.feature_engineer_.transform(X, y),
            index=X.index,
            columns=self.get_feature_names(),
        )

        if dropna:
            X_trans = X_trans[~np.isnan(X_trans).any(axis=1)]
        return X_trans

    def postprocess_predict(
        self,
        prediction: pd.DataFrame,
        X: pd.DataFrame,
        y: pd.Series,
        force_monotonic_quantiles: bool = False,
    ) -> pd.DataFrame:
        """
        Postprocessing function for the prediction result.

        Parameters
        ----------
        prediction : pd.DataFrame
            Dataframe containing the prediction.
        X : pd.DataFrame
            The training input samples.
        y : pd.Series
            The target values.
        force_monotonic_quantiles : bool, optional (default=False)
            whether to force quantiles to not overlap. When fitting multiple quantile regressions
            it is possible that individual quantile regression lines over-lap, or in other words,
            a quantile regression line fitted to a lower quantile predicts higher that a line
            fitted to a higher quantile. If this occurs for a certain prediction, the output
            distribution is invalid. In this function we force monotonicity by making the outer
            quantiles at least as high as the inner quantiles.

        Returns
        -------
        pd.DataFrame
            Postprocessed predictions.
        """
        # Put the predictions in a dataframe so we can undo the differencing
        prediction = pd.DataFrame(prediction, columns=self.prediction_cols_, index=X.index)

        # Undo the scaling
        # TODO: For each target differently...
        if self.y_scaler is not None:
            for output_col in [f"q_{q}" for q in self.quantiles] + ["mean"]:
                mask = prediction.columns.str.contains(output_col)
                sub_prediction = prediction.loc[:, mask]
                sub_prediction = pd.DataFrame(
                    self.y_scaler.inverse_transform(sub_prediction.values),
                    index=sub_prediction.index,
                    columns=sub_prediction.columns,
                )
                prediction.loc[:, mask] = sub_prediction

        # Undo the differencing
        if self.use_diff_of_y:
            prediction = inverse_differenced_target(prediction, y)

        if force_monotonic_quantiles:
            prediction = self.make_prediction_monotonic(prediction)

        return prediction

    def make_prediction_monotonic(self, prediction: pd.DataFrame) -> pd.DataFrame:
        """
        When fitting multiple quantile regressions it is possible that individual quantile
        regression lines over-lap, or in other words, a quantile regression line fitted to a lower
        quantile predicts higher that a line fitted to a higher quantile. If this occurs for a
        certain prediction, the output distribution is invalid. In this function we force
        monotonicity by making the outer quantiles at least as high as the inner quantiles.

        Parameters
        ----------
        prediction : pd.DataFrame
            Dataframe containing a prediction containing several quantiles

        Returns
        -------
        pd.DataFrame
            Prediction for which the quantiles are (now) monotonic
        """
        # Retrieve prediction columns and split them by group (predict ahead)
        grouped_cols = {}
        for p in self.predict_ahead:
            grouped_cols[p] = [
                [q, "predict_lead_{}_q_{}".format(p, q)]
                for q in self.quantiles
                if "predict_lead_{}_q_{}".format(p, q) in prediction.columns
            ]

        # Divide and order ascending
        lower_band_groups = []
        upper_band_groups = []
        for predict_ahead in grouped_cols:
            sorted_cols = grouped_cols[predict_ahead]
            sorted_cols.sort(key=itemgetter(0))
            upper_band = [x[1] for x in sorted_cols if x[0] > 0.5]
            lower_band = [x[1] for x in sorted_cols if x[0] < 0.5][::-1]
            if upper_band:
                upper_band_groups.append(upper_band)
            if lower_band:
                lower_band_groups.append(lower_band)

        # Upper band quantiles should monotonic increase, and lower band quantiles should
        # monotonic decrease
        for g in upper_band_groups:
            prediction[g] = make_df_monotonic(prediction[g], aggregate_func="max")
        for g in lower_band_groups:
            prediction[g] = make_df_monotonic(prediction[g], aggregate_func="min")

        return prediction

    def get_feature_names(self) -> list:
        """
        Function for obtaining feature names. Generally used instead of the attribute, and more
        compatible with the sklearn API.

        Returns
        -------
        list:
            list of feature names
        """
        return self.feature_engineer_.get_feature_names()

    def _set_input_cols(self, X: pd.DataFrame) -> None:
        """
        Function to set the attribute self._input_cols (input column names).
        Only used internally right before the feature building.
        Time column is not included, since time is always a dependency
        This can be used to determine model dependencies

        Parameters
        ----------
        X: pd.DataFrame
            The DataFrame that contains the input columns
        """
        col_names = X.columns.values
        col_names = col_names[col_names != self.timecol]
        self._input_cols = col_names

    def get_input_cols(self) -> np.array:
        """
        Function to obtain the input column names.
        This can be used to determine model dependencies
        Time column is not included, since time is always a dependency

        Returns
        -------
        list:
            The input column names
        """
        check_is_fitted(self, "_input_cols")
        return self._input_cols

    def get_actual(self, y: pd.Series) -> Union[pd.Series, pd.DataFrame]:
        """
        Convenience function for getting the actual values (perfect prediction).
        Mainly useful for scoring the model. This essentially does and undoes differencing
        on y, meaning this function will output what a perfect model would have outputted.
        If predict_ahead is 0, no differencing is done anyway, so y is just returned unchanged.

        Returns a Series of a Dataframe depending on the number of values in self.predict_ahead

        Parameters
        -------
        y:
            The target values

        Returns
        -------
        pd.Series or pd.DataFrame:
            y after applying differencing and undoing the process (if self.use_diff_of_y)
            If self.predict_ahead is a single value, this function will return a series.
            If self.predict_ahead has multiple values (list), this function will return a
            dataframe.
        """
        # This function only works if the estimator is fitted
        check_is_fitted(self, "model_")
        if len(self.predict_ahead) == 1:
            pred = self.predict_ahead[0]
        else:
            pred = self.predict_ahead

        if self.predict_ahead != [0]:
            actual = make_shifted_target(y, self.use_diff_of_y, pred)
            if self.use_diff_of_y:
                actual = inverse_differenced_target(actual, y)
        else:
            actual = y.copy().astype(float)

        return actual

    def score(self, X: pd.DataFrame, y: pd.Series) -> float:
        """
        Default score function. Uses sum of mse and tilted loss

        Parameters
        ----------
        X: pd.DataFrame
            The independent variables used to predict.
        y: pd.Series
            The target values

        Returns
        -------
        float:
            The score
        """
        # This function only works if the estimator is fitted
        check_is_fitted(self, "model_")
        # We need a dataframe, regardless of if these functions outputs a series or dataframe
        prediction = pd.DataFrame(self.predict(X, y))
        actual = pd.DataFrame(self.get_actual(y))

        # scale these predictions back to get a score that is in same units as keras loss
        if self.y_scaler is not None:
            pred_scaled = np.zeros_like(prediction)
            for i in range(prediction.shape[1]):
                pred_scaled[:, i] = self.y_scaler.transform(
                    prediction.iloc[:, i].values.reshape(-1, 1)
                ).ravel()
            prediction = pd.DataFrame(
                pred_scaled, columns=prediction.columns, index=prediction.index
            )

            actual = pd.DataFrame(
                self.y_scaler.transform(actual.values).ravel(),
                index=actual.index,
                columns=actual.columns,
            )

        # actual usually has some missings at the end
        # prediction usually has some missings at the beginning
        # We ignore the rows with missings
        actual, missing = remove_target_nan(prediction, actual, use_x=True)

        # self.prediction_cols_[-1] defines the mean prediction
        # For n outputs, we need the last n columns instead
        # Therefore, this line calculates the mse of the mean prediction
        mean_prediction = prediction[self.prediction_cols_[-1 * len(self.predict_ahead) :]].values
        # Calculate the MSE of all the predictions, and tilted loss of quantile predictions,
        # then sum them at the end
        loss = np.sum(np.mean((actual - mean_prediction) ** 2, axis=0))
        for i, q in enumerate(self.quantiles):
            startcol = len(self.predict_ahead) * i
            endcol = startcol + len(self.predict_ahead)
            e = np.array(actual - prediction[self.prediction_cols_[startcol:endcol]].values)
            # Calculate all the quantile losses, and sum them at the end
            loss += np.sum(np.mean(np.max([q * e, (q - 1) * e], axis=0), axis=0))
        return loss

    @abstractmethod
    def dump(self, foldername: str, prefix: str = "model") -> None:
        """Save a model to disk

        This abstract method needs to be implemented by any class inheriting from
        SamQuantileRegressor. This function dumps the SAM model to disk.

        Parameters
        ----------
        foldername : str
            The folder location where to save the model
        prefix : str, optional
           The prefix used in the filename, by default "model"
        """
        return None

    @classmethod
    @abstractmethod
    def load(cls, foldername, prefix="model") -> Callable:
        """Load a model from disk

        This abstract method needs to be implemented by any class inheriting from
        SamQuantileRegressor. This function loads a SAM model from disk.

        Parameters
        ----------
        foldername : str
            The folder location where the model is stored
        prefix : str, optional
           The prefix used in the filename, by default "model"

        Returns
        -------
        The SAM model that has been loaded from disk
        """
        return None
