import openmeteo_requests
import streamlit as sl
import pandas as pd
import datetime
import requests_cache
from retry_requests import retry

# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

# Make sure all required weather variables are listed here
# The order of variables in hourly or daily is important to assign them correctly below
url = "https://historical-forecast-api.open-meteo.com/v1/forecast"
twoDays = datetime.date.today() - datetime.timedelta(days=2)

params = {
	"latitude": 52.374,
	"longitude": 4.8897,
	"start_date": "2021-01-01",
	"end_date": twoDays,
	"daily": ["weather_code", "temperature_2m_max", "temperature_2m_min", "daylight_duration", "rain_sum"],
	"hourly": "temperature_2m",
}
responses = openmeteo.weather_api(url, params=params)

# Process 5 locations
for response in responses:
	print(f"\nCoordinates: {response.Latitude()}°N {response.Longitude()}°E")
	print(f"Elevation: {response.Elevation()} m asl")
	print(f"Timezone: {response.Timezone()}{response.TimezoneAbbreviation()}")
	print(f"Timezone difference to GMT+0: {response.UtcOffsetSeconds()}s")

	# Process daily data. The order of variables needs to be the same as requested.
	daily = response.Daily()
	daily_weather_code = daily.Variables(0).ValuesAsNumpy()
	daily_temperature_2m_max = daily.Variables(1).ValuesAsNumpy()
	daily_temperature_2m_min = daily.Variables(2).ValuesAsNumpy()
	daily_daylight_duration = daily.Variables(3).ValuesAsNumpy()
	daily_rain_sum = daily.Variables(4).ValuesAsNumpy()

	daily_data = {"date": pd.date_range(
		start = pd.to_datetime(daily.Time(), unit = "s", utc = True),
		end = pd.to_datetime(daily.TimeEnd(), unit = "s", utc = True),
		freq = pd.Timedelta(seconds = daily.Interval()),
		inclusive = "left"
	)}

	daily_data["weather_code"] = daily_weather_code
	daily_data["temperature_2m_max"] = daily_temperature_2m_max
	daily_data["temperature_2m_min"] = daily_temperature_2m_min
	daily_data["daylight_duration"] = daily_daylight_duration
	daily_data["rain_sum"] = daily_rain_sum

	daily_dataframe = pd.DataFrame(data = daily_data)
sl.title("Min temperatuur in Nederland")
sl.line_chart(daily_dataframe.set_index('date')['temperature_2m_min'])

