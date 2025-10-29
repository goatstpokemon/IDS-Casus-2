import openmeteo_requests
import streamlit as sl
import pandas as pd
import streamlit_shadcn_ui as ui
# Setup the Open-Meteo API client with cache and retry on error
openmeteo = openmeteo_requests.Client()


url = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# inspiratie bron: https://discuss.streamlit.io/t/label-and-values-in-in-selectbox/1436/5
locations = {
    "De Bilt": (52.11, 5.1806),
    "Leeuwarden": (53.2014, 5.8086),
    "Zandvoort": (52.3713, 4.5331),
    "Maastricht": (50.8483, 5.6889),
    "Enschede": (52.2183, 6.8958),
}
sl.markdown("# Homepagina 🦩")
# city = sl.selectbox("Selecteer locatie", options=list(locations.keys()))
city = ui.tabs(options=['De Bilt', 'Leeuwarden', 'Zandvoort', 'Maastricht', 'Enschede'], default_value='De Bilt', key="location_tabs")






lat, lon = locations[city]
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

     

sl.header(f"Neerslag in {city}")
sl.bar_chart(data=daily_data, x="date", y="rain_sum", y_label="Totaal regenval", x_label="Datum")


min_temp = int(daily_dataframe['temperature_2m_min'].min())
max_temp = int(daily_dataframe['temperature_2m_max'].max())

temp_range = sl.slider(
	"Temperatuur bereik in ℃", max_value=max_temp, min_value=min_temp, value=(min_temp, max_temp),
	step=1
)

min,max = temp_range
filtered = daily_dataframe[(daily_data['temperature_2m_min'] >= min) & (daily_data['temperature_2m_max'] <= max)].copy()

sl.line_chart(data=filtered, x="date", y=['temperature_2m_min', 'temperature_2m_max'],color=["#7AC2EC","#BB4648" ])


# Bereken de gemiddelde dagtemperatuur
filtered['temperature_2m_mean'] = (filtered['temperature_2m_min'] + filtered['temperature_2m_max']) / 2

# Maak een line chart met de gemiddelde temperatuur en de regenval
sl.header(f"Gemiddelde Temperatuur en Regenval in {city}")
sl.line_chart(
    data=filtered,
    x="date",
    y=['temperature_2m_mean', 'rain_sum'],
    color=["#5DADE2", "#2ECC71"]  # Voorbeeldkleuren: blauw voor temp, groen voor regen
)


import requests_cache
from retry_requests import retry
import numpy as np
import pandas as pd
import openmeteo_requests 
import streamlit as sl 
import folium 
from streamlit_folium import folium_static 

# --- 1. Setup en API Parameters Aanpassen ---
cache_session = requests_cache.CachedSession('.cache', expire_after = 3600)
retry_session = retry(cache_session, retries = 5, backoff_factor = 0.2)
openmeteo = openmeteo_requests.Client(session = retry_session)

url = "https://api.open-meteo.com/v1/forecast"
params = {
    "latitude": [52.1, 50.8483, 52.2183, 53.2014, 52.3713],
    "longitude": [5.1833, 5.6889, 6.8958, 5.8086, 4.5331],
    "hourly": "precipitation_probability",
    # NIEUW: Voeg de huidige temperatuur (op 2m hoogte) toe
    "current": "temperature_2m", 
    "forecast_days": 1,
}
responses = openmeteo.weather_api(url, params=params)

# Definieer de steden (aanname voor de coördinaten)
locations_info = [
    {"city": "De Bilt", "lat": 52.1, "lon": 5.1833},
    {"city": "Maastricht", "lat": 50.8483, "lon": 5.6889},
    {"city": "Enschede", "lat": 52.2183, "lon": 6.8958},
    {"city": "Leeuwarden", "lat": 53.2014, "lon": 5.8086},
    {"city": "Zandvoort", "lat": 52.3713, "lon": 4.5331},
]

summary_data = []

# --- 2. Dataverwerking, inclusief Huidige Temperatuur ---
for i, response in enumerate(responses):
    city_info = locations_info[i]
    
    # Haal de huidige temperatuur op uit het 'current' blok
    current = response.Current()
    # De temperatuur variabele is de eerste (index 0) in het 'current' blok
    current_temperature = current.Variables(0).Value() 
    
    # Bereken Gem. Neerslagkans (zoals eerder)
    hourly = response.Hourly()
    hourly_precipitation_probability = hourly.Variables(0).ValuesAsNumpy()
    mean_precipitation_probability = np.mean(hourly_precipitation_probability)
    
    # Voeg alle data toe aan de samenvatting
    summary_data.append({
        "city": city_info["city"],
        "lat": response.Latitude(),
        "lon": response.Longitude(),
        "Huidige Temp. (°C)": f"{current_temperature:.1f}", # Nieuw veld
        "Gem. Kans Neerslag (%)": f"{mean_precipitation_probability:.2f}"
    })

summary_df = pd.DataFrame(summary_data)

# --- 3. Streamlit Weergave met Folium Pop-up Updaten ---

sl.header("Weersverwachting Overzicht 🌦️")
sl.subheader("Interactieve Kaart met Weerdata")

# Bepaal het midden van de kaart voor de initiële weergave
center_lat = summary_df['lat'].mean()
center_lon = summary_df['lon'].mean()

# Maak een Folium kaart aan
m = folium.Map(location=[center_lat, center_lon], zoom_start=7)

# Voeg markers toe met bijgewerkte pop-up
for index, row in summary_df.iterrows():
    # NIEUW: De tekst die in de pop-up verschijnt bevat nu beide waarden
    popup_html = f"""
    <h4>{row['city']}</h4>
    <hr style='margin: 5px 0;'>
    <b>Huidige Temperatuur:</b> {row['Huidige Temp. (°C)']}°C<br>
    <b>Gemiddelde Neerslagkans:</b> {row['Gem. Kans Neerslag (%)']}%
    """
    
    folium.Marker(
        location=[row['lat'], row['lon']],
        popup=folium.Popup(popup_html, max_width=300),
        tooltip=f"{row['city']}: {row['Huidige Temp. (°C)']}°C" # Korte tooltip bij hoveren
    ).add_to(m)

# Toon de Folium kaart in Streamlit
folium_static(m)




# Choose rain types




















# sl.header(f"Gemiddelde zonlichturen in {city}")
# daily_dataframe["year"] = daily_dataframe["date"].dt.year
# daily_dataframe["month"] = daily_dataframe["date"].dt.month
# year = sl.selectbox(
#     "Selecteer jaar",
#     options=sorted(daily_dataframe["year"].unique()),
# )

# filtered = daily_dataframe[
#     (daily_dataframe["year"] == year) & (daily_dataframe["month"] == month)
# ].copy()

# sl.line_chart(
#     data=filtered,
#     x="date",
#     y="daylight_duration",
#     y_label="Gemiddelde zonlichturen",
#     x_label="Datum",
#     color="#F8C57C",
# )
# sl.map(data=daily_data)