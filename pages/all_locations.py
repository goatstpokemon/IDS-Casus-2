import streamlit as st
import pandas as pd
import numpy as np
import openmeteo_requests

# -------- Open-Meteo setup --------
openmeteo = openmeteo_requests.Client()
url = "https://historical-forecast-api.open-meteo.com/v1/forecast"

locations: dict[str, tuple[float, float]] = {
    "De Bilt": (52.11, 5.1806),
    "Leeuwarden": (53.2014, 5.8086),
    "Zandvoort": (52.3713, 4.5331),
    "Maastricht": (50.8483, 5.6889),
    "Enschede": (52.2183, 6.8958),
}


# ---------- Function to fetch data ----------
@st.cache_data(show_spinner=False)
def load_city_data(name: str, lat: float, lon: float) -> pd.DataFrame:
    """Fetch historical weather data for a city and return as DataFrame."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2021-01-01",
        "end_date": "2025-01-01",
        "daily": [
            "weather_code",
            "temperature_2m_max",
            "temperature_2m_min",
            "daylight_duration",
            "rain_sum",
        ],
        "hourly": "temperature_2m",
        # Optional: set timezone if you want local dates instead of UTC
        # "timezone": "Europe/Amsterdam",
    }

    responses = openmeteo.weather_api(url, params=params)
    if not responses:
        return pd.DataFrame(
            columns=[
                "date",
                "weather_code",
                "temperature_2m_max",
                "temperature_2m_min",
                "daylight_duration",
                "rain_sum",
            ]
        )

    resp = responses[0]
    daily = resp.Daily()

    # Build date index from API metadata
    dates = pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s", utc=True),
        end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left",
    )

    daily_data = {
        "date": dates,
        "weather_code": daily.Variables(0).ValuesAsNumpy(),
        "temperature_2m_max": daily.Variables(1).ValuesAsNumpy(),
        "temperature_2m_min": daily.Variables(2).ValuesAsNumpy(),
        "daylight_duration": daily.Variables(3).ValuesAsNumpy(),
        "rain_sum": daily.Variables(4).ValuesAsNumpy(),
    }

    df = pd.DataFrame(daily_data)
    # Ensure types
    df["date"] = pd.to_datetime(df["date"])
    for col in [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "daylight_duration",
        "rain_sum",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


# ----------- Sidebar: location checkboxes -----------
st.sidebar.header("Kies locaties voor vergelijking")
choices = {loc: st.sidebar.checkbox(loc, value=False) for loc in locations}
selected = [loc for loc, checked in choices.items() if checked]

if not selected:
    st.info("Selecteer minimaal één locatie in de zijbalk om grafieken te zien.")
    st.stop()

st.title("Vergelijk Temperatuur & Regenval per Locatie")

# ----------- Fetch data for selected locations -----------
data_per_city: dict[str, pd.DataFrame] = {}
for city in selected:
    lat, lon = locations[city]
    data_per_city[city] = load_city_data(city, lat, lon)

# Guard: if any city failed to load
if not data_per_city:
    st.error("Kon geen data ophalen.")
    st.stop()

# ----------- Dynamic temperature slider -----------
# Compute global min/max across selected cities
all_mins = []
all_maxs = []
for df_city in data_per_city.values():
    if not df_city.empty:
        if "temperature_2m_min" in df_city and "temperature_2m_max" in df_city:
            all_mins.append(np.nanmin(df_city["temperature_2m_min"].values))
            all_maxs.append(np.nanmax(df_city["temperature_2m_max"].values))

if not all_mins or not all_maxs:
    st.error("Geen temperatuurdata beschikbaar voor de selectie.")
    st.stop()

global_min = float(np.nanmin(all_mins))
global_max = float(np.nanmax(all_maxs))

# Make slider integer-based but covering the range safely
slider_min = int(np.floor(global_min))
slider_max = int(np.ceil(global_max))

tmin, tmax = st.slider(
    "Temperatuur bereik (°C) – Filter alle grafieken",
    min_value=slider_min,
    max_value=slider_max,
    value=(slider_min, slider_max),
    step=1,
)

# ----------- Show charts in columns -----------
cols = st.columns(len(selected))

for city, col in zip(selected, cols):
    df_city = data_per_city[city]

    # Filter by slider range
    filtered = df_city[
        (df_city["temperature_2m_min"] >= tmin)
        & (df_city["temperature_2m_max"] <= tmax)
    ].copy()

    with col:
        st.subheader(city)
        if filtered.empty:
            st.write("Geen data binnen het gekozen bereik.")
            continue

        st.line_chart(
            data=filtered,
            x="date",
            y=["temperature_2m_max", "temperature_2m_min"],
            color=["#BB4648", "#7AC2EC"],
        )
        st.bar_chart(
            data=filtered,
            x="date",
            y="rain_sum",
        )