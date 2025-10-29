from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import matplotlib.pylab as plt
from matplotlib.pylab import rcParams
from statsmodels.tsa.statespace.sarimax import SARIMAX
import openmeteo_requests as omr
import requests_cache
from retry_requests import retry

cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = omr.Client(session=retry_session)

# Fetch historical data
url_historical = (
    "https://historical-forecast-api.open-meteo.com/v1/forecast"
)
params_historical = {
    "latitude": 52.11,
    "longitude": 5.1806,
    "start_date": "2025-10-13",
    "end_date": "2025-10-27",
    "hourly": ["temperature_2m", "precipitation", "wind_speed_10m"],
}
responses_historical = openmeteo.weather_api(
    url_historical, params=params_historical
)

response_historical = responses_historical[0]
if not responses_historical:
    raise ValueError("No response received from the weather API.")

hourly = response_historical.Hourly()
hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
hourly_precipitation = hourly.Variables(1).ValuesAsNumpy()
hourly_wind_speed_10m = hourly.Variables(2).ValuesAsNumpy()
hourly_data = {
    "date": pd.date_range(
        start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
        end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=hourly.Interval()),
        inclusive="left",
    )
}
hourly_data["temperature_2m"] = hourly_temperature_2m
hourly_data["precipitation"] = hourly_precipitation
hourly_data["wind_speed_10m"] = hourly_wind_speed_10m

hourly_dataframe = pd.DataFrame(data=hourly_data)
hourly_dataframe = hourly_dataframe.dropna()
hourly_dataframe = hourly_dataframe.set_index("date")
hourly_dataframe = hourly_dataframe.asfreq("h")
hourly_dataframe = hourly_dataframe.sort_index()

print("Historical data shape:", hourly_dataframe.shape)
print(hourly_dataframe.head())

# Fetch 48-hour forecast from Open-Meteo
url_forecast = "https://api.open-meteo.com/v1/forecast"
params_forecast = {
    "latitude": 52.11,
    "longitude": 5.1806,
    "hourly": ["temperature_2m", "precipitation", "wind_speed_10m"],
    "forecast_hours": 48,
    "timezone": "UTC",
}
responses_forecast = openmeteo.weather_api(
    url_forecast, params=params_forecast
)
response_forecast = responses_forecast[0]

hourly_forecast = response_forecast.Hourly()
forecast_temperature = hourly_forecast.Variables(0).ValuesAsNumpy()
forecast_precipitation = hourly_forecast.Variables(1).ValuesAsNumpy()
forecast_wind = hourly_forecast.Variables(2).ValuesAsNumpy()

forecast_dates = pd.date_range(
    start=pd.to_datetime(hourly_forecast.Time(), unit="s", utc=True),
    periods=len(forecast_temperature),
    freq="h",
)
forecast_dataframe = pd.DataFrame(
    {
        "date": forecast_dates,
        "temperature_2m": forecast_temperature,
        "precipitation": forecast_precipitation,
        "wind_speed_10m": forecast_wind,
    }
)
forecast_dataframe = forecast_dataframe.set_index("date")

print("\nOpen-Meteo forecast:")
print(forecast_dataframe.head())

# SARIMAX with exogenous variables (wind + precipitation)
def sarimax_forecast_exog(
    dataframe, column, order, seasonal_order, steps, exog_cols
):
    print("Fitting SARIMAX model with exogenous variables...")
    exog = dataframe[exog_cols]
    model = SARIMAX(
        dataframe[column],
        exog=exog,
        order=order,
        seasonal_order=seasonal_order,
    )
    model_fit = model.fit(disp=False)
    return model_fit

# SARIMAX univariate (temperature only)
def sarimax_forecast_univariate(
    dataframe, column, order, seasonal_order, steps
):
    print("Fitting univariate SARIMAX model...")
    model = SARIMAX(
        dataframe[column], order=order, seasonal_order=seasonal_order
    )
    model_fit = model.fit(disp=False)
    return model_fit

order = (1, 1, 1)
seasonal_order = (1, 1, 1, 24)
steps = 48
exog_cols = ["precipitation", "wind_speed_10m"]

# Fit both models
model_univariate = sarimax_forecast_univariate(
    hourly_dataframe, "temperature_2m", order, seasonal_order, steps
)
model_exog = sarimax_forecast_exog(
    hourly_dataframe, "temperature_2m", order, seasonal_order, steps, exog_cols
)

# Generate forecasts with exogenous data
last_date = hourly_dataframe.index[-1]
forecast_dates_idx = pd.date_range(
    start=last_date + timedelta(hours=1), periods=steps, freq="h"
)

# Univariate forecast
sarimax_pred_univariate = model_univariate.forecast(steps=steps)
sarimax_pred_univariate.index = forecast_dates_idx

# Exogenous forecast (with wind + precipitation)
sarimax_pred_exog = model_exog.forecast(
    steps=steps, exog=forecast_dataframe[exog_cols]
)
sarimax_pred_exog.index = forecast_dates_idx

# Calculate metrics
mae_univariate = np.mean(
    np.abs(
        sarimax_pred_univariate.values
        - forecast_dataframe["temperature_2m"].values
    )
)
rmse_univariate = np.sqrt(
    np.mean(
        (
            sarimax_pred_univariate.values
            - forecast_dataframe["temperature_2m"].values
        )
        ** 2
    )
)

mae_exog = np.mean(
    np.abs(
        sarimax_pred_exog.values - forecast_dataframe["temperature_2m"].values
    )
)
rmse_exog = np.sqrt(
    np.mean(
        (
            sarimax_pred_exog.values
            - forecast_dataframe["temperature_2m"].values
        )
        ** 2
    )
)

print(f"\n=== Benchmark Results ===")
print(f"\nUnivariate SARIMAX (temp only):")
print(f"  MAE: {mae_univariate:.4f}°C")
print(f"  RMSE: {rmse_univariate:.4f}°C")
print(f"\nSARIMAX with Exogenous (temp + wind + precip):")
print(f"  MAE: {mae_exog:.4f}°C")
print(f"  RMSE: {rmse_exog:.4f}°C")
print(f"\nImprovement: {((mae_univariate - mae_exog) / mae_univariate * 100):.2f}% (lower is better)")

# Plot comparison
rcParams["figure.figsize"] = 16, 8
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10))

# Temperature forecast comparison
ax1.plot(
    hourly_dataframe.index[-168:],
    hourly_dataframe["temperature_2m"][-168:],
    label="Historical Data (Last 7 days)",
    color="blue",
    linewidth=2,
)
ax1.plot(
    forecast_dataframe.index,
    forecast_dataframe["temperature_2m"],
    label="Open-Meteo Forecast",
    color="green",
    marker="o",
    linewidth=2,
    markersize=4,
)
ax1.plot(
    sarimax_pred_univariate.index,
    sarimax_pred_univariate.values,
    label="SARIMAX (Univariate)",
    color="red",
    marker="s",
    linewidth=2,
    markersize=4,
)
ax1.plot(
    sarimax_pred_exog.index,
    sarimax_pred_exog.values,
    label="SARIMAX (w/ Exog: Wind + Precip)",
    color="purple",
    marker="^",
    linewidth=2.5,
    markersize=5,
)
ax1.set_xlabel("Date", fontsize=12)
ax1.set_ylabel("Temperature (°C)", fontsize=12)
ax1.set_title(
    "Temperature Forecast Comparison: 48h Ahead",
    fontsize=14,
    fontweight="bold",
)
ax1.legend(fontsize=10, loc="best")
ax1.grid(True, alpha=0.3)

# Forecast error comparison
errors_om = (
    forecast_dataframe["temperature_2m"] - forecast_dataframe["temperature_2m"]
).values
errors_univariate = (
    sarimax_pred_univariate.values - forecast_dataframe["temperature_2m"].values
)
errors_exog = (
    sarimax_pred_exog.values - forecast_dataframe["temperature_2m"].values
)

ax2.plot(
    sarimax_pred_univariate.index,
    errors_univariate,
    label="SARIMAX Error (Univariate)",
    color="red",
    marker="s",
    linewidth=2,
    markersize=4,
)
ax2.plot(
    sarimax_pred_exog.index,
    errors_exog,
    label="SARIMAX Error (w/ Exog)",
    color="purple",
    marker="^",
    linewidth=2.5,
    markersize=5,
)
ax2.axhline(y=0, color="black", linestyle="--", alpha=0.5)
ax2.set_xlabel("Date", fontsize=12)
ax2.set_ylabel("Forecast Error (°C)", fontsize=12)
ax2.set_title("Prediction Error: Univariate vs Exogenous", fontsize=14, fontweight="bold")
ax2.legend(fontsize=10, loc="best")
ax2.grid(True, alpha=0.3)

plt.tight_layout()
plt.show()