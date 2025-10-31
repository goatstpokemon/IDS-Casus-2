import requests_cache
from retry_requests import retry
import numpy as np
import pandas as pd
import openmeteo_requests
import streamlit as st
import folium
from streamlit_folium import folium_static
import streamlit_shadcn_ui as ui
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
import requests
import imageio
from PIL import Image, ImageDraw
from sarimax import generate_sarimax_forecast
from branca.element import MacroElement
from jinja2 import Template
# Cache session setup
cache_session = requests_cache.CachedSession(
    ".cache", expire_after=3600
)
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
    0: "Helder", 1: "Vrijwel helder", 2: "Gedeeltelijk bewolkt",
    3: "Bewolkt", 45: "Mist", 48: "Mist met rijp",
    51: "Motregen: Licht", 53: "Motregen: Matig",
    55: "Motregen: Dicht", 56: "Vriesende motregen: Licht",
    57: "Vriesende motregen: Dicht", 61: "Regen: Licht",
    63: "Regen: Matig", 65: "Regen: Zwaar",
    66: "Vriesende regen: Licht", 67: "Vriesende regen: Zwaar",
    71: "Sneeuwval: Licht", 73: "Sneeuwval: Matig",
    75: "Sneeuwval: Zwaar", 77: "Sneeuwkorrels",
    80: "Buien: Licht", 81: "Buien: Matig", 82: "Buien: Hevig",
    85: "Sneeuwbuien: Licht", 86: "Sneeuwbuien: Zwaar"
}

CITY_IMAGES = {
    "de bilt": "http://photos.wikimapia.org/p/00/07/60/84/26_full.jpg",
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

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="Weer Dashboard Nederland",
    page_icon="🌤️",
    layout="wide"
)

st.title("Weer Dashboard Nederland")
st.markdown(
    "Interactief weersdashboard met real-time data, prognoses en "
    "historische analyses voor steden in Nederland."
)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_city_image(city):
    return CITY_IMAGES.get(city.lower(), "")

def weather_code_to_description(code):
    return WEATHER_CODES.get(code, "Onbekend")

def get_current_weather(lat, lon):
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
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ["temperature_2m", "precipitation",
                "wind_speed_10m"],
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
    return pd.DataFrame({
        "date": pd.date_range(
            start=pd.to_datetime(
                daily.Time(), unit="s", utc=True
            ),
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

@st.cache_data(ttl=600)
def fetch_temperature_grid():
    """Fetch temperatuurgegevens voor raster over Nederland."""
    url = "https://api.open-meteo.com/v1/forecast"
    lats = np.linspace(50.75, 53.5, 15)
    lons = np.linspace(3.4, 7.2, 15)
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    lat_flat = lat_grid.flatten()
    lon_flat = lon_grid.flatten()

    temps = []
    for lat, lon in zip(lat_flat, lon_flat):
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m",
            "timezone": "Europe/Amsterdam"
        }
        resp = requests.get(url, params=params)
        temps.append(resp.json()["current"]["temperature_2m"])

    temp_grid = np.array(temps).reshape(lat_grid.shape)
    return lon_grid, lat_grid, temp_grid

@st.cache_data(ttl=600)
def generate_rain_animation():
    """
    Generate animated rain clouds GIF voor Nederland (20 minuten).
    Fetch hourly precipitation forecast en create frames.
    """
    # Get hourly precipitation for center of Netherlands
    center_lat = 52.11
    center_lon = 5.1806

    params = {
        "latitude": center_lat,
        "longitude": center_lon,
        "hourly": "precipitation",
        "forecast_days": 1,
    }

    res = openmeteo.weather_api(API_URLS["current"], params=params)
    hourly = res[0].Hourly()
    precip_data = hourly.Variables(0).ValuesAsNumpy()[:4]

    # Normalize precipitation for visualization
    max_precip = max(precip_data) if max(precip_data) > 0 else 1
    precip_norm = (precip_data / max_precip * 255).astype(int)

    frames = []
    for idx, precip in enumerate(precip_norm):
        img = Image.new("RGB", (600, 400), color=(135, 206, 235))
        draw = ImageDraw.Draw(img)

        # Draw gradient background based on precipitation
        color = (50 + precip // 5, 100 + precip // 10,
                150 + precip // 20)
        draw.rectangle([0, 0, 600, 400], fill=color)

        # Draw rain clouds (circles)
        cloud_positions = [
            (150, 100), (450, 150), (300, 250), (100, 300)
        ]
        for cx, cy in cloud_positions:
            offset = int(20 * np.sin(idx * np.pi / 4))
            draw.ellipse(
                [cx - 40 + offset, cy - 30, cx + 40 + offset, cy + 30],
                fill=(169, 169, 169)
            )

        # Draw rain drops
        for _ in range(precip // 10 + 5):
            x = np.random.randint(0, 600)
            y = np.random.randint(0, 400)
            draw.line([(x, y), (x - 2, y + 10)], fill=(0, 100, 255),
                    width=2)

        frames.append(np.array(img))

    # Save as GIF
    gif_path = "/rain_animation.gif"
    imageio.mimsave(gif_path, frames, duration=0.5)

    return gif_path

# ============================================================================
# SECTIE 1: TEMPERATUURKAART NEDERLAND
# ============================================================================

st.header("Temperatuurkaart Nederland")
st.markdown(
    "Actuele temperatuurverdeling over Nederland met CartoPy "
    "visualisatie."
)

with st.spinner("Temperatuurkaart wordt geladen..."):
    lon_grid, lat_grid, temp_grid = fetch_temperature_grid()

    fig, ax = plt.subplots(
        figsize=(14, 10),
        subplot_kw={
            "projection": ccrs.Stereographic(
                central_latitude=52.1,
                central_longitude=5.3
            )
        }
    )

    ax.set_extent([3.4, 7.2, 50.75, 53.5], crs=ccrs.PlateCarree())
    ax.add_feature(cfeature.BORDERS, linewidth=0.5)
    ax.add_feature(cfeature.COASTLINE, linewidth=0.5)
    ax.gridlines(draw_labels=False, alpha=0.3)

    cf = ax.contourf(
        lon_grid, lat_grid, temp_grid,
        cmap="coolwarm",
        transform=ccrs.PlateCarree(),
        levels=15
    )
    cbar = plt.colorbar(cf, ax=ax, orientation="vertical", pad=0.02)
    cbar.set_label("Temperatuur (°C)")
    ax.set_title("Nederland — Huidige Temperatuur")

    st.pyplot(fig)

col1, col2, col3 = st.columns(3)
col1.metric("Min Temperatuur", f"{temp_grid.min():.1f}°C")
col2.metric("Gemiddelde Temperatuur", f"{temp_grid.mean():.1f}°C")
col3.metric("Max Temperatuur", f"{temp_grid.max():.1f}°C")

st.divider()

# ============================================================================
# SECTIE 3: INTERACTIEVE KAART MET WEERDATA
# ============================================================================

st.header("Weersverwachting Overzicht")
st.markdown(
    "Interactieve kaart met huidige weergegevens voor alle "
    "geselecteerde steden."
)
st.header("Selecteer een Locatie")
st.markdown("Kies een stad voor gedetailleerde weergegevens.")

city = ui.tabs(
    options=list(LOCATIONS.keys()),
    default_value="De Bilt",
    key="location_tabs"
)
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
    summary_data.append({
        "city": city_info["city"],
        "lat": response.Latitude(),
        "lon": response.Longitude(),
        "temperature": current.Variables(0).Value(),
        "precipitation": current.Variables(1).Value(),
        "precipitation_probability": current.Variables(2).Value(),
    })

summary_df = pd.DataFrame(summary_data)

center_lat = summary_df["lat"].mean()
center_lon = summary_df["lon"].mean()

m = folium.Map(location=[center_lat, center_lon], zoom_start=7)

for _, row in summary_df.iterrows():
    popup_html = f"""
    <h4>{row['city']}</h4>
    <hr style='margin: 5px 0;'>
    <b>Temperatuur:</b> {row['temperature']:.1f}°C<br>
    <b>Neerslag:</b> {row['precipitation']:.1f} mm<br>
    <b>Neerslagkans:</b> {row['precipitation_probability']:.0f}%
    """
    marker_color = "red" if row["city"] == city else "blue"

    folium.Marker(
        location=[row["lat"], row["lon"]],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=f"{row['city']}: {row['temperature']:.1f}°C, {row['precipitation']:.1f}mm",
        icon=folium.Icon(color=marker_color, icon="")
    ).add_to(m)

class FloatLegend(MacroElement):
    _template = Template(u"""
        {% macro html(this, kwargs) %}
        <div id='{{this.get_name()}}' style="
            position: fixed;
            bottom: 30px;
            left: 30px;
            z-index: 9999;
            background: white;
            padding: 10px 12px;
            border: 1px solid #bbb;
            border-radius: 4px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
            font-size: 14px;
            line-height: 1.4;
        ">
          <div style="font-weight: 600; margin-bottom: 6px;">Legenda</div>
          <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
            <span style="display:inline-block; width:14px; height:14px; background:#d33; border-radius:3px;"></span>
            <span>Huidige locatie</span>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="display:inline-block; width:14px; height:14px; background:#2a81cb; border-radius:3px;"></span>
            <span>Overige locaties</span>
          </div>
        </div>
        {% endmacro %}
    """)

    def __init__(self, name=None):
        super().__init__()
        self._name = name or "float_legend"


m.add_child(FloatLegend())
folium_static(m)

st.divider()

# ============================================================================
# SECTIE 4: LOCATIE SELECTIE & HUIDGE WEER
# ============================================================================



lat, lon = LOCATIONS[city]
st.subheader(f"Huidige Weer in {city}")
image_url = get_city_image(city)
if image_url:
    st.image(image_url, use_container_width=True)
    st.markdown(f"#### bron: {image_url}")
    st.html('''<style>
        div[data-testid="stImageContainer"] img {
            max-height: 300px;
            object-fit: cover;
        }
    </style>''')

current_weather = get_current_weather(lat, lon)
hourly_weather = get_hourly_weather(lat, lon)
historical_weather = get_historical_weather(lat, lon)


cols = st.columns(3)

with cols[0]:
    with ui.card(key="card1"):
        ui.element("p", "Temperatuur",
                className="text-sm text-neutral-400 mb-1")
        temp = int(current_weather["temperature_2m"][0])
        ui.element("div", f"{temp}℃",
                className="text-3xl font-bold")

with cols[1]:
    with ui.card(key="card2"):
        ui.element("p", "Neerslag",
                className="text-sm text-neutral-400 mb-1")
        precip = int(current_weather["precipitation"][0])
        ui.element("div", f"{precip} mm",
                className="text-3xl font-bold")

with cols[2]:
    with ui.card(key="card3"):
        ui.element("p", "Weercode",
                className="text-sm text-neutral-400 mb-1")
        code = int(current_weather["weather_code"][0])
        description = weather_code_to_description(code)
        ui.element("div", description,
                className="text-lg font-medium")

st.divider()

# ============================================================================
# SECTIE 5: DAGVERLOPEN & HISTORISCHE DATA
# ============================================================================

st.header("Weergegevens van Vandaag")

st.subheader(f"Neerslag in {city}")
st.bar_chart(data=hourly_weather, y="precipitation",
            color="#4A90E2", use_container_width=True)

st.subheader(f"Temperatuur in {city}")
st.line_chart(data=hourly_weather, y="temperature_2m",
            color="#E94E77", use_container_width=True)

st.subheader(f"Windsnelheid in {city}")
st.line_chart(data=hourly_weather, y="wind_speed_10m",
            color="#50E3C2", use_container_width=True)

st.divider()

st.header("Historische Gegevens")

st.subheader(f"Neerslag in {city}")
st.bar_chart(data=historical_weather, x="date", y="rain_sum",
            use_container_width=True)

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

st.subheader(f"Min/Max Temperatuur in {city}")
st.line_chart(
    data=filtered,
    x="date",
    y=["temperature_2m_min", "temperature_2m_max"],
    color=["#7AC2EC", "#BB4648"],
    use_container_width=True
)

filtered["temperature_2m_mean"] = (
    (filtered["temperature_2m_min"] +
    filtered["temperature_2m_max"]) / 2
)

st.subheader(f"Gemiddelde Temperatuur en Regenval in {city}")
st.line_chart(
    data=filtered,
    x="date",
    y=["temperature_2m_mean", "rain_sum"],
    color=["#5DADE2", "#2ECC71"],
    use_container_width=True
)

st.divider()

# ============================================================================
# SECTIE 6: SARIMAX FORECAST
# ============================================================================

st.header("Temperatuurverwachting (48 uur)")

try:
    with st.spinner(
        f"SARIMAX-Model wordt voor {city} berekend..."
    ):
        forecast_result = generate_sarimax_forecast(
            lat, lon, hours=48, use_exog=True
        )

    comparison_df = pd.DataFrame({
        "Open-Meteo": forecast_result["actual"][
            "temperature_2m"
        ].values,
        "SARIMAX (Univariate)": (
            forecast_result["univariate"].values
        ),
        "SARIMAX (met Wind & Regen)": (
            forecast_result["forecast"].values
        ),
        "ARMA Model": forecast_result["arma"].values,
        "AR Model": forecast_result["ar"].values,
    }, index=forecast_result["actual"].index)

    row1 = st.columns(4)
    row2 = st.columns(4)
    metrics = forecast_result["metrics"]

    with row1[0]:
        with ui.card(key="metric_mae_uni"):
            ui.element("p", "MAE Alleen Temp",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['mae_univariate']:.2f}°C",
                className="text-lg font-medium"
            )

    with row1[1]:
        with ui.card(key="metric_mae_exog"):
            ui.element("p", "MAE met wind & regen",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['mae_exog']:.2f}°C",
                className="text-lg font-medium"
            )

    with row1[2]:
        with ui.card(key="metric_mae_arma"):
            ui.element("p", "MAE ARMA Model",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['mae_arma']:.2f}°C",
                className="text-lg font-medium"
            )

    with row1[3]:
        with ui.card(key="metric_mae_ar"):
            ui.element("p", "MAE AR Model",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['mae_ar']:.2f}°C",
                className="text-lg font-medium"
            )

    with row2[0]:
        with ui.card(key="metric_rmse_uni"):
            ui.element("p", "RMSE alleen temp",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['rmse_univariate']:.2f}°C",
                className="text-lg font-medium"
            )

    with row2[1]:
        with ui.card(key="metric_rmse_exog"):
            ui.element("p", "RMSE (met wind & regen)",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['rmse_exog']:.2f}°C",
                className="text-lg font-medium"
            )

    with row2[2]:
        with ui.card(key="metric_rmse_arma"):
            ui.element("p", "RMSE ARMA Model",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['rmse_arma']:.2f}°C",
                className="text-lg font-medium"
            )

    with row2[3]:
        with ui.card(key="metric_rmse_ar"):
            ui.element("p", "RMSE AR Model",
                    className="text-xs text-neutral-400 mb-1")
            ui.element(
                "div",
                f"{metrics['rmse_ar']:.2f}°C",
                className="text-lg font-medium"
            )

    model_distances = {
        "SARIMAX (Univariate)": np.mean(
            np.abs(
                forecast_result["univariate"].values -
                forecast_result["actual"]["temperature_2m"].values
            )
        ),
        "SARIMAX (met Wind & Regen)": np.mean(
            np.abs(
                forecast_result["forecast"].values -
                forecast_result["actual"]["temperature_2m"].values
            )
        ),
        "ARMA Model": np.mean(
            np.abs(
                forecast_result["arma"].values -
                forecast_result["actual"]["temperature_2m"].values
            )
        ),
        "AR Model": np.mean(
            np.abs(
                forecast_result["ar"].values -
                forecast_result["actual"]["temperature_2m"].values
            )
        ),
    }

    best_model = min(model_distances, key=model_distances.get)
    best_distance = model_distances[best_model]

    st.markdown(
        f"**Beste Model:** {best_model} "
    )
    st.markdown(
        f"**Beste Model:** {best_model} "
        f"(gemiddelde afwijking: {best_distance:.2f}°C)"
    )

    st.subheader("Temperatuurvergelijking: 48u Voorspelling")
    st.line_chart(
        data=comparison_df,
        color=["#2ECC71", "#E74C3C", "#9B59B6",
            "#3498DB", "#F1C40F"],
        use_container_width=True,
    )

    st.subheader("Voorspelling met Historische Context")
    last_7_days = forecast_result["historical"][-168:].copy()
    last_7_days.columns = ["Historisch", "Precip", "Wind"]

    combined = pd.concat([
        last_7_days[["Historisch"]],
        comparison_df,
    ], axis=0)

    st.line_chart(
        data=combined,
        use_container_width=True,
    )

except Exception as e:
    st.error(
        f"Fout bij het berekenen van de voorspelling: {str(e)}"
    )

st.subheader("Bronnen")
st.markdown(
    "- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)\n"
    "- [Streamlit Documentation](https://docs.streamlit.io/)"
)