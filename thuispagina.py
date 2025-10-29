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
cache_session = requests_cache.CachedSession(".cache", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
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
    {"city": "De Bilt", "lat": 52.11, "lon": 5.1806},
    {"city": "Maastricht", "lat": 50.8483, "lon": 5.6889},
    {"city": "Enschede", "lat": 52.2183, "lon": 6.8958},
    {"city": "Leeuwarden", "lat": 53.2014, "lon": 5.8086},
    {"city": "Zandvoort", "lat": 52.3713, "lon": 4.5331},
]

WEATHER_CODES = {
    0: "Helder",
    1: "Vrijwel helder",
    2: "Gedeeltelijk bewolkt",
    3: "Bewolkt",
    45: "Mist",
    48: "Mist met rijp",
    51: "Motregen: Licht",
    53: "Motregen: Matig",
    55: "Motregen: Dicht",
    56: "Vriesende motregen: Licht",
    57: "Vriesende motregen: Dicht",
    61: "Regen: Licht",
    63: "Regen: Matig",
    65: "Regen: Zwaar",
    66: "Vriesende regen: Licht",
    67: "Vriesende regen: Zwaar",
    71: "Sneeuwval: Licht",
    73: "Sneeuwval: Matig",
    75: "Sneeuwval: Zwaar",
    77: "Sneeuwkorrels",
    80: "Buien: Licht",
    81: "Buien: Matig",
    82: "Buien: Hevig",
    85: "Sneeuwbuien: Licht",
    86: "Sneeuwbuien: Zwaar"
}

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

API_URLS = {
    "historical": (
        "https://historical-forecast-api.open-meteo.com/v1/forecast"
    ),
    "current": "https://api.open-meteo.com/v1/forecast"
}

# Page Config
st.set_page_config(
    page_title="Weer Dashboard Nederland",
    page_icon="🌤️",
    layout="wide"
)

st.title("Weer Dashboard Nederland 🌤️")


# Helper Functions
def get_city_image(city):
    """Get city image URL by city name."""
    return CITY_IMAGES.get(city.lower(), "")


def weather_code_to_description(code):
    """Convert weather code to description."""
    return WEATHER_CODES.get(code, "Onbekend")


def get_current_weather(lat, lon):
    """Fetch current weather for a location."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "wind_direction_10m",
            "weather_code",
            "precipitation",
        ],
    }
    res = openmeteo.weather_api(API_URLS["current"], params=params)
    current = res[0].Current()
    return pd.DataFrame({
        "temperature_2m": [current.Variables(0).Value()],
        "precipitation": [current.Variables(1).Value()],
        "weather_code": [current.Variables(2).Value()],
    })


def get_hourly_weather(lat, lon):
    """Fetch hourly weather for today."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["temperature_2m", "precipitation", "wind_speed_10m"],
        "forecast_days": 1,
    }
    res = openmeteo.weather_api(API_URLS["current"], params=params)
    hourly = res[0].Hourly()
    return pd.DataFrame({
        "temperature_2m": hourly.Variables(0).ValuesAsNumpy(),
        "precipitation": hourly.Variables(1).ValuesAsNumpy(),
        "wind_speed_10m": hourly.Variables(2).ValuesAsNumpy(),
    })


def get_historical_weather(lat, lon):
    """Fetch historical weather data."""
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
    }
    res = openmeteo.weather_api(API_URLS["historical"], params=params)
    daily = res[0].Daily()

    return pd.DataFrame({
        "date": pd.date_range(
            start=pd.to_datetime(daily.Time(), unit="s", utc=True),
            end=pd.to_datetime(daily.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=daily.Interval()),
            inclusive="left"
        ),
        "weather_code": daily.Variables(0).ValuesAsNumpy(),
        "temperature_2m_max": daily.Variables(1).ValuesAsNumpy(),
        "temperature_2m_min": daily.Variables(2).ValuesAsNumpy(),
        "daylight_duration": daily.Variables(3).ValuesAsNumpy(),
        "rain_sum": daily.Variables(4).ValuesAsNumpy(),
    })


# City Selection
city = ui.tabs(
    options=list(LOCATIONS.keys()),
    default_value="De Bilt",
    key="location_tabs"
)

lat, lon = LOCATIONS[city]

# Display City Image
image_url = get_city_image(city)
if image_url:
    st.image(image_url, use_container_width=True)
    st.html('''<style>
        div[data-testid="stImageContainer"] img {
            max-height: 300px;
            object-fit: cover;
        }
    </style>''')

# Fetch Data for Selected City
current_weather = get_current_weather(lat, lon)
hourly_weather = get_hourly_weather(lat, lon)
historical_weather = get_historical_weather(lat, lon)

# Display Current Weather
st.header(f"Huidige weer in {city}")
cols = st.columns(3)

with cols[0]:
    with ui.card(key="card1"):
        ui.element(
            "p",
            "Huidige temperatuur",
            className="text-[2rem] text-neutral-400 mb-1"
        )
        temp = int(current_weather["temperature_2m"][0])
        ui.element("div", f"{temp} ℃",
                   className="text-2xl font-medium")

with cols[1]:
    with ui.card(key="card2"):
        ui.element(
            "p",
            "Huidige neerslag",
            className="text-[2rem] text-neutral-400 mb-1"
        )
        precip = int(current_weather["precipitation"][0])
        ui.element("div", f"{precip} mm",
                   className="text-2xl font-medium")

with cols[2]:
    with ui.card(key="card3"):
        ui.element(
            "p",
            "Huidige weercode",
            className="text-[2rem] text-neutral-400 mb-1"
        )
        code = int(current_weather["weather_code"][0])
        description = weather_code_to_description(code)
        ui.element("div", description,
                   className="text-2xl font-medium")

# Display Today's Weather
st.header(f"Weer van vandaag in {city}")
st.bar_chart(
    data=hourly_weather,
    y="precipitation",
    color="#4A90E2",
    y_label="Neerslag (mm)",
    x_label="Uur",
    use_container_width=True
)
st.line_chart(
    data=hourly_weather,
    y="temperature_2m",
    color="#E94E77",
    y_label="Temperatuur (℃)",
    x_label="Uur",
    use_container_width=True
)
st.line_chart(
    data=hourly_weather,
    y="wind_speed_10m",
    color="#50E3C2",
    y_label="Windsnelheid (km/u)",
    x_label="Uur",
    use_container_width=True
)

# Display Rainfall
st.header(f"Neerslag in {city}")
st.bar_chart(
    data=historical_weather,
    x="date",
    y="rain_sum",
    use_container_width=True
)

# Temperature Filter
min_temp = int(historical_weather["temperature_2m_min"].min())
max_temp = int(historical_weather["temperature_2m_max"].max())

temp_range = st.slider(
    "Temperatuur bereik in ℃",
    min_value=min_temp,
    max_value=max_temp,
    value=(min_temp, max_temp),
    step=1
)

min_selected, max_selected = temp_range
filtered = historical_weather[
    (historical_weather["temperature_2m_min"] >= min_selected) &
    (historical_weather["temperature_2m_max"] <= max_selected)
].copy()

st.line_chart(
    data=filtered,
    x="date",
    y=["temperature_2m_min", "temperature_2m_max"],
    color=["#7AC2EC", "#BB4648"],
    use_container_width=True
)

# Mean Temperature and Rainfall
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

# Multi-City Map with Current Weather
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
    API_URLS["current"],
    params=params_current
)

summary_data = []

for i, response in enumerate(responses_current):
    city_info = LOCATIONS_INFO[i]
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

# Create Map
center_lat = summary_df["lat"].mean()
center_lon = summary_df["lon"].mean()

m = folium.Map(location=[center_lat, center_lon], zoom_start=7)

# Add markers with precipitation
for _, row in summary_df.iterrows():
    popup_html = f"""
    <h4>{row['city']}</h4>
    <hr style='margin: 5px 0;'>
    <b>Huidige Temperatuur:</b> {row['temperature']:.1f}°C<br>
    <b>Neerslag:</b> {row['precipitation']:.1f} mm<br>
    <b>Neerslagkans:</b> {row['precipitation_probability']:.0f}%
    """

    marker_color = "red" if row["city"] == city else "blue"

    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=(
            f"{row['city']}: {row['temperature']:.1f}°C, "
            f"{row['precipitation']:.1f}mm"
        ),
        icon=folium.Icon(color=marker_color, icon="")
    ).add_to(m)

folium_static(m)