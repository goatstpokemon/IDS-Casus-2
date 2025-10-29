from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import openmeteo_requests as omr
import requests_cache
from retry_requests import retry
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.ar_model import AutoReg
from statsmodels.tsa.arima.model import ARIMA

cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = omr.Client(session=retry_session)

URL_HISTORICAL = (
    "https://historical-forecast-api.open-meteo.com/v1/forecast"
)
URL_FORECAST = "https://api.open-meteo.com/v1/forecast"


def fetch_historical_data(lat, lon, days=14):

    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days)

    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "hourly": ["temperature_2m", "precipitation", "wind_speed_10m"],
    }
    responses = openmeteo.weather_api(URL_HISTORICAL, params=params)
    response = responses[0]

    hourly = response.Hourly()
    data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        ),
        "temperature_2m": hourly.Variables(0).ValuesAsNumpy(),
        "precipitation": hourly.Variables(1).ValuesAsNumpy(),
        "wind_speed_10m": hourly.Variables(2).ValuesAsNumpy(),
    }
    df = pd.DataFrame(data)
    df = df.dropna().set_index("date").asfreq("h").sort_index()
    return df


def fetch_forecast_data(lat, lon, hours=48):

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["temperature_2m", "precipitation", "wind_speed_10m"],
        "forecast_hours": hours,
        "timezone": "UTC",
    }
    responses = openmeteo.weather_api(URL_FORECAST, params=params)
    response = responses[0]

    hourly = response.Hourly()
    forecast_dates = pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        periods=len(hourly.Variables(0).ValuesAsNumpy()),
        freq="h",
    )
    df = pd.DataFrame(
        {
            "date": forecast_dates,
            "temperature_2m": hourly.Variables(0).ValuesAsNumpy(),
            "precipitation": hourly.Variables(1).ValuesAsNumpy(),
            "wind_speed_10m": hourly.Variables(2).ValuesAsNumpy(),
        }
    )
    return df.set_index("date")


def fit_ar_model(df, column, lags=24):

    model = AutoReg(df[column], lags=lags)
    return model.fit()


def fit_arma_model(df, column, order=(1, 1)):

    model = ARIMA(df[column], order=(order[0], 0, order[1]))
    return model.fit()


def fit_sarimax_univariate(df, column, order, seasonal_order):

    model = SARIMAX(
        df[column], order=order, seasonal_order=seasonal_order
    )

    return model.fit(disp=False)


def fit_sarimax_exog(df, column, order, seasonal_order, exog_cols):

    exog = df[exog_cols]
    model = SARIMAX(
        df[column],
        exog=exog,
        order=order,
        seasonal_order=seasonal_order,
    )
    return model.fit(disp=False)


def generate_sarimax_forecast(
    lat, lon, hours=48, order=(1, 1, 1),
    seasonal_order=(1, 1, 1, 24), use_exog=True
):

    # Fetch data
    historical = fetch_historical_data(lat, lon, days=14)
    forecast_actual = fetch_forecast_data(lat, lon, hours=hours)

    # Fit models
    model_uni = fit_sarimax_univariate(
        historical, "temperature_2m", order, seasonal_order
    )
    model_exog = fit_sarimax_exog(
        historical, "temperature_2m", order,
        seasonal_order, ["precipitation", "wind_speed_10m"]
    )
    model_ar = fit_ar_model(historical, "temperature_2m", lags=24)
    model_arma = fit_arma_model(historical, "temperature_2m",
                                order=(1, 1))


    # Generate forecasts
    last_date = historical.index[-1]
    forecast_idx = pd.date_range(
        start=last_date + timedelta(hours=1), periods=hours, freq="h"
    )

    pred_uni = model_uni.forecast(steps=hours)
    pred_uni.index = forecast_idx

    pred_exog = model_exog.forecast(
        steps=hours,
        exog=forecast_actual[["precipitation", "wind_speed_10m"]]
    )
    pred_exog.index = forecast_idx

    pred_ar = model_ar.forecast(steps=hours)
    pred_ar.index = forecast_idx

    pred_arma = model_arma.forecast(steps=hours)
    pred_arma.index = forecast_idx

    # Calculate metrics
    actual_temps = forecast_actual["temperature_2m"].values
    mae_uni = np.mean(np.abs(pred_uni.values - actual_temps))
    rmse_uni = np.sqrt(np.mean((pred_uni.values - actual_temps) ** 2))
    mae_exog = np.mean(np.abs(pred_exog.values - actual_temps))
    rmse_exog = np.sqrt(np.mean((pred_exog.values - actual_temps) ** 2))
    mae_ar = np.mean(np.abs(pred_ar.values - actual_temps))
    rmse_ar = np.sqrt(np.mean((pred_ar.values - actual_temps) ** 2))
    mae_arma = np.mean(np.abs(pred_arma.values - actual_temps))
    rmse_arma = np.sqrt(np.mean((pred_arma.values - actual_temps) ** 2))

    model_choice = pred_exog if use_exog else pred_uni

    return {
        "forecast": model_choice,
        "actual": forecast_actual,
        "univariate": pred_uni,
        "ar": pred_ar,
        "arma": pred_arma,
        "metrics": {
            "mae_univariate": mae_uni,
            "rmse_univariate": rmse_uni,
            "mae_exog": mae_exog,
            "rmse_exog": rmse_exog,
            "mae_ar": mae_ar,
            "rmse_ar": rmse_ar,
            "mae_arma": mae_arma,
            "rmse_arma": rmse_arma,
        },
        "historical": historical,
    }