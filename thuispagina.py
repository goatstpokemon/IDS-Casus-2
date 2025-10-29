import requests_cache
from retry_requests import retry
import numpy as np
import pandas as pd
import openmeteo_requests
import streamlit as st
import folium
from streamlit_folium import folium_static
import streamlit_shadcn_ui as ui

# Setup the Open-Meteo API client with cache and retry on error
cache_session = requests_cache.CachedSession(
    ".cache",
    expire_after=3600
)
retry_session = retry(
    cache_session,
    retries=5,
    backoff_factor=0.2
)
openmeteo = openmeteo_requests.Client(session=retry_session)

# Constants
LOCATIONS = {
    "De Bilt": (52.11, 5.1806),
    "Leeuwarden": (53.2014, 5.8086),
    "Zandvoort": (52.3713, 4.5331),
    "Maastricht": (50.8483, 5.6889),
    "Enschede": (52.2183, 6.8958),
}

LOCATIONS_INFO = [
    {"city": "De Bilt", "lat": 52.1, "lon": 5.1833},
    {"city": "Maastricht", "lat": 50.8483, "lon": 5.6889},
    {"city": "Enschede", "lat": 52.2183, "lon": 6.8958},
    {"city": "Leeuwarden", "lat": 53.2014, "lon": 5.8086},
    {"city": "Zandvoort", "lat": 52.3713, "lon": 4.5331},
]

CITY_IMAGES = {
    "de bilt": (
        "http://photos.wikimapia.org/p/00/07/60/84/26_full.jpg"
    ),
    "leeuwarden": (
        "https://www.aguidetoleeuwarden.nl/wp-content/uploads/"
        "2016/06/0Z3A7603-WEB-1024x682.jpg"
    ),
    "zandvoort": (
        "https://rp-online.de/imgs/32/1/6/9/4/9/0/5/6/1/"
        "tok_5fcfaf997293bbffd903385d52bce392/"
        "w2100_h1313_x1500_y1000_DPA_bfunk_dpa_5FA1FE00C50C84E7"
        "-50f8a09b4238adf1.jpg"
    ),
    "maastricht": (
        "https://lp-cms-production.imgix.net/2019-06/"
        "GettyImages-514855827_super.jpg?fit=crop&q=40&sharp=10"
        "&vib=20&auto=format&ixlib=react-8.6.4"
    ),
    "enschede": (
        "https://media.indebuurt.nl/enschede/2021/03/08134301/"
        "oude-markt-enschede-scaled.jpg"
    )
}

HISTORICAL_URL = (
    "https://historical-forecast-api.open-meteo.com/v1/forecast"
)
CURRENT_URL = "https://api.open-meteo.com/v1/forecast"

# --- Page Config ---
st.set_page_config(
    page_title="Weer Dashboard Nederland",
    page_icon="🌤️",
    layout="wide"
)

st.title("Weer Dashboard Nederland 🌤️")


# --- Helper Functions ---
def get_city_image(city):
    """Get city image URL by city name."""
    return CITY_IMAGES.get(city.lower(), "")


# --- City Selection ---
city = ui.tabs(
    options=list(LOCATIONS.keys()),
    default_value="De Bilt",
    key="location_tabs"
)

lat, lon = LOCATIONS[city]

# --- Display City Image ---
image_url = get_city_image(city)
if image_url:
    st.image(image_url, use_container_width=True)
    st.html('''<style>
        div[data-testid="stImageContainer"] img {
            max-height: 300px;
            object-fit: cover;
        }
    </style>''')

st.header(f"Huidige weer in {city}")

# --- Fetch Historical Data for Selected City ---
params_historical = {
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
}

response_historical = openmeteo.weather_api(
    HISTORICAL_URL,
    params=params_historical
)
daily = response_historical[0].Daily()

daily_weather_code = daily.Variables(0).ValuesAsNumpy()
daily_temperature_2m_max = daily.Variables(1).ValuesAsNumpy()
daily_temperature_2m_min = daily.Variables(2).ValuesAsNumpy()
daily_daylight_duration = daily.Variables(3).ValuesAsNumpy()
daily_rain_sum = daily.Variables(4).ValuesAsNumpy()

daily_data = {
    "date": pd.date_range(
        start=pd.to_datetime(daily.Time(), unit="s", utc=True),
        end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
        freq=pd.Timedelta(seconds=daily.Interval()),
        inclusive="left"
    ),
    "weather_code": daily_weather_code,
    "temperature_2m_max": daily_temperature_2m_max,
    "temperature_2m_min": daily_temperature_2m_min,
    "daylight_duration": daily_daylight_duration,
    "rain_sum": daily_rain_sum,
}

daily_dataframe = pd.DataFrame(data=daily_data)

# --- Display Rainfall ---
st.header(f"Neerslag in {city}")
st.bar_chart(
    data=daily_dataframe,
    x="date",
    y="rain_sum",
    use_container_width=True
)

# --- Temperature Filter ---
min_temp = int(daily_dataframe["temperature_2m_min"].min())
max_temp = int(daily_dataframe["temperature_2m_max"].max())

temp_range = st.slider(
    "Temperatuur bereik in ℃",
    max_value=max_temp,
    min_value=min_temp,
    value=(min_temp, max_temp),
    step=1
)

min_selected, max_selected = temp_range
filtered = daily_dataframe[
    (daily_dataframe["temperature_2m_min"] >= min_selected) &
    (daily_dataframe["temperature_2m_max"] <= max_selected)
].copy()

st.line_chart(
    data=filtered,
    x="date",
    y=["temperature_2m_min", "temperature_2m_max"],
    color=["#7AC2EC", "#BB4648"],
    use_container_width=True
)

# --- Mean Temperature and Rainfall ---
filtered["temperature_2m_mean"] = (
    (filtered["temperature_2m_min"] +
     filtered["temperature_2m_max"]) / 2
)

st.header(f"Gemiddelde Temperatuur en Regenval in {city}")
st.line_chart(
    data=filtered,
    x="date",
    y=["temperature_2m_mean", "rain_sum"],
    color=["#5DADE2", "#2ECC71"],
    use_container_width=True
)

# --- Multi-City Map with Current Weather ---
st.header("Weersverwachting Overzicht 🌦️")
st.subheader("Interactieve Kaart met Weerdata")

# Fetch current weather for all cities
params_current = {
    "latitude": [loc["lat"] for loc in LOCATIONS_INFO],
    "longitude": [loc["lon"] for loc in LOCATIONS_INFO],
    "current": [
        "temperature_2m",
        "precipitation",
        "precipitation_probability"
    ],
    "forecast_days": 1,
}

responses_current = openmeteo.weather_api(
    CURRENT_URL,
    params=params_current
)

summary_data = []

for i, response in enumerate(responses_current):
    city_info = LOCATIONS_INFO[i]

    # Get current data
    current = response.Current()
    current_temperature = current.Variables(0).Value()
    current_precipitation = current.Variables(1).Value()
    current_precipitation_prob = current.Variables(2).Value()

    summary_data.append({
        "city": city_info["city"],
        "lat": response.Latitude(),
        "lon": response.Longitude(),
        "temperature": current_temperature,
        "precipitation": current_precipitation,
        "precipitation_probability": current_precipitation_prob,
    })

summary_df = pd.DataFrame(summary_data)

# --- Create Map ---
center_lat = summary_df["lat"].mean()
center_lon = summary_df["lon"].mean()

m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=7
)

# Add markers with precipitation
for _, row in summary_df.iterrows():
    popup_html = f"""
    <h4>{row['city']}</h4>
    <hr style='margin: 5px 0;'>
    <b>Huidige Temperatuur:</b> {row['temperature']:.1f}°C<br>
    <b>Neerslag:</b> {row['precipitation']:.1f} mm<br>
    <b>Neerslagkans:</b> {row['precipitation_probability']:.0f}%
    """

    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=(
            f"{row['city']}: {row['temperature']:.1f}°C, "
            f"{row['precipitation']:.1f}mm"
        )
    ).add_to(m)

folium_static(m)