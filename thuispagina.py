import openmeteo_requests
import streamlit as sl
import pandas as pd
import streamlit_shadcn_ui as ui

# Initialize API client
openmeteo = openmeteo_requests.Client()

# Constants
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

LOCATIONS = {
    "De Bilt": (52.11, 5.1806),
    "Leeuwarden": (53.2014, 5.8086),
    "Zandvoort": (52.3713, 4.5331),
    "Maastricht": (50.8483, 5.6889),
    "Enschede": (52.2183, 6.8958),
}

API_URLS = {
    "historical": "https://historical-forecast-api.open-meteo.com/v1/forecast",
    "current": "https://api.open-meteo.com/v1/forecast"
}
sl.set_page_config(
	page_title="Weer Dashboard Nederland",
	page_icon="🌤️",
	layout="wide"
)
# Helper functions
def weather_code_to_description(code):
    return WEATHER_CODES.get(code, "Onbekend")

def get_current_weather(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "wind_direction_10m",
                    "weather_code", "precipitation", "wind_speed_10m"],
    }
    res = openmeteo.weather_api(API_URLS["current"], params=params)
    current = res[0].Current()
    return pd.DataFrame({
        "temperature_2m": [current.Variables(0).Value()],
        "precipitation": [current.Variables(1).Value()],
        "weather_code": [current.Variables(2).Value()],
        "wind_speed_10m": [current.Variables(3).Value()],
    })

def get_hourly_weather(lat, lon):
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

    df = pd.DataFrame({
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
    return df

# UI
sl.title("Weer Dashboard Nederland")

ui.element("p",
		   "Bekijk het huidige weer, het weer van vandaag en historische neerslaggegevens voor verschillende locaties in Nederland.",
		   className="text-lg text-neutral-500 mb-4")

city = ui.tabs(
    options=list(LOCATIONS.keys()),
    default_value="De Bilt",
    key="location_tabs"
)

lat, lon = LOCATIONS[city]

# Fetch data
current_weather = get_current_weather(lat, lon)
hourly_weather = get_hourly_weather(lat, lon)
historical_weather = get_historical_weather(lat, lon)
def get_city_image(city):
      city_images = {
        "leeuwarden": "https://www.aguidetoleeuwarden.nl/wp-content/uploads/2016/06/0Z3A7603-WEB-1024x682.jpg",
        "de bilt": "http://photos.wikimapia.org/p/00/07/60/84/26_full.jpg",
        "zandvoort": "https://rp-online.de/imgs/32/1/6/9/4/9/0/5/6/1/tok_5fcfaf997293bbffd903385d52bce392/w2100_h1313_x1500_y1000_DPA_bfunk_dpa_5FA1FE00C50C84E7-50f8a09b4238adf1.jpg",
        "maastricht": "https://lp-cms-production.imgix.net/2019-06/GettyImages-514855827_super.jpg?fit=crop&q=40&sharp=10&vib=20&auto=format&ixlib=react-8.6.4",
        "enschede": "https://media.indebuurt.nl/enschede/2021/03/08134301/oude-markt-enschede-scaled.jpg"
    }
      return city_images.get(city.lower(), "")

# Display current weather
sl.image(get_city_image(city), width='stretch')
sl.header(f"Huidige weer in {city}")

sl.html('''<style>
        div[data-testid="stImageContainer"] img {
          max-height: 300px;
          object-fit: cover;
        }</style>
        ''')

cols = sl.columns(4)

with cols[0]:
    with ui.card(key="card1"):
        ui.element("p", "Huidige temperatuur",
                   className="text-[2rem] text-neutral-400 mb-1")
        temp = int(current_weather["temperature_2m"][0])
        ui.element("div", f"{temp} ℃",
                   className="text-2xl font-medium")

with cols[1]:
    with ui.card(key="card2"):
        ui.element("p", "Huidige neerslag",
                   className="text-[2rem] text-neutral-400 mb-1")
        precip = int(current_weather["precipitation"][0])
        ui.element("div", f"{precip} mm",
                   className="text-2xl font-medium")

with cols[2]:
    with ui.card(key="card3"):
        ui.element("p", "Huidige weercode",
                   className="text-[2rem] text-neutral-400 mb-1")
        code = int(current_weather["weather_code"][0])
        description = weather_code_to_description(code)
        ui.element("div", description,
                   className="text-2xl font-medium")
with cols[3]:
	with ui.card(key="card4"):
		ui.element("p", "Huidige windsnelheid",
				   className="text-[2rem] text-neutral-400 mb-1")
		wind_speed = float(current_weather["wind_speed_10m"][0])
		ui.element("div", f"{wind_speed} km/u",
				   className="text-2xl font-medium")



# Display today's weather
sl.header(f"Weer van vandaag in {city}")
sl.bar_chart(data=hourly_weather, y="precipitation", color="#4A90E2",
             y_label="Neerslag (mm)", x_label="Uur",
             use_container_width=True)
sl.line_chart(data=hourly_weather, y="temperature_2m", color="#E94E77",
              y_label="Temperatuur (℃)", x_label="Uur",
              use_container_width=True)
sl.line_chart(data=hourly_weather, y="wind_speed_10m", color="#50E3C2",
              y_label="Windsnelheid (km/u)", x_label="Uur",
              use_container_width=True)

# Display historical data
sl.header(f"Neerslag in {city}")
sl.bar_chart(data=historical_weather, x="date", y="rain_sum",
             y_label="Totaal regenval (mm)", x_label="Datum",
             use_container_width=True)

# Temperature filter
min_temp = int(historical_weather["temperature_2m_min"].min())
max_temp = int(historical_weather["temperature_2m_max"].max())

temp_range = sl.slider(
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
]

sl.line_chart(
    data=filtered,
    x="date",
    y=["temperature_2m_min", "temperature_2m_max"],
    color=["#7AC2EC", "#BB4648"]
)