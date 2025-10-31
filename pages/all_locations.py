import streamlit as st
import pandas as pd
import numpy as np
import openmeteo_requests

st.title("Weer steden vergelijken in Nederland")

openmeteo = openmeteo_requests.Client()
url = "https://historical-forecast-api.open-meteo.com/v1/forecast"

locations: dict[str, tuple[float, float]] = {
    "De Bilt": (52.11, 5.1806),
    "Leeuwarden": (53.2014, 5.8086),
    "Zandvoort": (52.3713, 4.5331),
    "Maastricht": (50.8483, 5.6889),
    "Enschede": (52.2183, 6.8958),
}


@st.cache_data(show_spinner=False)
def load_city_data(name: str, lat: float, lon: float) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2021-01-01",
        "end_date": "2025-08-31",
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
    df["date"] = pd.to_datetime(df["date"])
    for col in [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "daylight_duration",
        "rain_sum",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["t_mean"] = (df["temperature_2m_max"] + df["temperature_2m_min"]) / 2.0
    df["diurnal_range"] = df["temperature_2m_max"] - df["temperature_2m_min"]
    df["is_wet_day"] = (df["rain_sum"] >= 1.0).astype(int)

    return df


def detect_heatwaves(
    df: pd.DataFrame,
    threshold: float = 25.0,
    min_days: int = 5,
    extreme_threshold: float = 30.0,
    min_extreme_days: int = 3,
) -> tuple[pd.DataFrame, int]:
    df = df.copy()
    df["in_heatwave"] = False

    if "temperature_2m_max" not in df.columns:
        return df, 0

    above_threshold = (df["temperature_2m_max"] >= threshold).astype(int)
    above_extreme = (df["temperature_2m_max"] >= extreme_threshold).astype(int)

    group_starts = (above_threshold.diff() == 1).fillna(False)
    heatwave_count = 0

    for idx in df[group_starts].index:
        start_pos = df.index.get_loc(idx)
        consecutive_count = 0
        extreme_count = 0
        for i in range(start_pos, len(above_threshold)):
            if above_threshold.iloc[i] == 1:
                consecutive_count += 1
                if above_extreme.iloc[i] == 1:
                    extreme_count += 1
            else:
                break

        if consecutive_count >= min_days and extreme_count >= min_extreme_days:
            df.loc[
                idx : df.index[start_pos + consecutive_count - 1], "in_heatwave"
            ] = True
            heatwave_count += 1

    return df, heatwave_count


def longest_dry_spell_days(df: pd.DataFrame) -> int:
    if df.empty or "rain_sum" not in df:
        return 0
    dry = df["rain_sum"].fillna(0) < 1.0
    if dry.sum() == 0:
        return 0
    groups = (dry != dry.shift()).cumsum()
    longest = (
        dry.groupby(groups).transform("size")[dry].max()
        if dry.any()
        else 0
    )
    return int(longest or 0)


st.sidebar.header("Kies locaties voor vergelijking")
choices = {loc: st.sidebar.checkbox(loc, value=False) for loc in locations}
selected = [loc for loc, checked in choices.items() if checked]

if not selected:
    st.info("Selecteer minimaal één locatie in de zijbalk om grafieken te zien.")
    st.stop()

st.title("Vergelijk Temperatuur & Regenval per Locatie")

data_per_city: dict[str, pd.DataFrame] = {}
heatwave_counts: dict[str, int] = {}
longest_dry_spells: dict[str, int] = {}

for city in selected:
    lat, lon = locations[city]
    df_city = load_city_data(city, lat, lon)
    df_city, hw_count = detect_heatwaves(df_city, threshold=25.0, min_days=5)
    data_per_city[city] = df_city
    heatwave_counts[city] = hw_count
    longest_dry_spells[city] = longest_dry_spell_days(df_city)

if not data_per_city:
    st.error("Kon geen data ophalen.")
    st.stop()

total_heatwaves = sum(heatwave_counts.values())
st.metric("Totaal aantal heatwaves (alle locaties)", total_heatwaves)

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

slider_min = int(np.floor(global_min))
slider_max = int(np.ceil(global_max))

tmin, tmax = st.slider(
    "Temperatuur bereik (°C) – Filter alle grafieken",
    min_value=slider_min,
    max_value=slider_max,
    value=(slider_min, slider_max),
    step=1,
)

view = st.radio(
    "Weergave",
    options=["Dagelijks", "Maandelijks"],
    index=0,
    horizontal=True,
    help="Schakel tussen dagelijkse gegevens en maandelijkse aggregaties.",
)

cols = st.columns(len(selected))

for city, col in zip(selected, cols):
    df_city = data_per_city[city]

    filtered = df_city[
        (df_city["temperature_2m_min"] >= tmin)
        & (df_city["temperature_2m_max"] <= tmax)
    ].copy()

    with col:
        st.subheader(city)
        st.caption(
            f"Heatwaves: {heatwave_counts[city]} • Langste droge periode: {longest_dry_spells[city]} dagen"
        )

        if filtered.empty:
            st.write("Geen data binnen het gekozen bereik.")
            continue

        metrics_cols = st.columns(3)
        with metrics_cols[0]:
            st.metric(
                "Grootste temperatuur verschil (°C)",
                f"{np.nanmax(filtered['diurnal_range']):.1f}",
            )
        with metrics_cols[1]:
            pleasant_days = int(
                np.sum((filtered["t_mean"] >= 22.0) & (filtered["t_mean"] <= 25.0))
            )
            st.metric("Korte broekweer", pleasant_days)
        with metrics_cols[2]:
            st.metric(
                "Procent natte dagen (%)",
                f"{np.nanmean(filtered['is_wet_day'] * 100):.1f}%",
            )

        # Yearly wet-day counts within the filtered window
        yr = filtered.copy()
        yr["year"] = yr["date"].dt.year
        wet_days_yearly = (
            (yr["rain_sum"] >= 1.0)
            .groupby(yr["year"])
            .sum()
            .astype(int)
            .reset_index(name="wet_days")
        )
        st.bar_chart(wet_days_yearly, x="year", y="wet_days")

        if view == "Dagelijks":
            st.line_chart(
                data=filtered,
                x="date",
                y=["temperature_2m_max", "temperature_2m_min"],
                color=["#BB4648", "#7AC2EC"],
            )

            st.line_chart(
                data=filtered,
                x="date",
                y=["t_mean", "diurnal_range"],
            )

            st.bar_chart(
                data=filtered,
                x="date",
                y="rain_sum",
            )

            hw = filtered.copy()
            hw["hw_tmax"] = np.where(
                hw["in_heatwave"], hw["temperature_2m_max"], np.nan
            )
            st.line_chart(
                data=hw,
                x="date",
                y=["hw_tmax"],
            )

        else:
            m = filtered.copy()
            m["month"] = m["date"].dt.to_period("M").dt.to_timestamp()
            monthly = (
                m.groupby("month")
                .agg(
                    t_mean=("t_mean", "mean"),
                    tmin=("temperature_2m_min", "mean"),
                    tmax=("temperature_2m_max", "mean"),
                    diurnal_range=("diurnal_range", "mean"),
                    rain_sum=("rain_sum", "sum"),
                    wet_days=("is_wet_day", "sum"),
                )
                .reset_index()
            )

            st.line_chart(monthly, x="month", y=["t_mean", "diurnal_range"])
            st.bar_chart(monthly, x="month", y="rain_sum")
            st.bar_chart(monthly, x="month", y="wet_days")
            st.line_chart(monthly, x="month", y=["tmin", "tmax"])




st.header("Analysevragen")
st.markdown(
    "- Welke stad had de meeste heatwaves en wat was de langste?\n"
    "- Zijn droge periodes langer aan land dan aan de kust?\n"
    "- Welke stad heeft de grootste diurnale range in de zomer?\n"
    "- Voor hetzelfde temp-bereik: welke stad heeft vaker een natte dag?\n"
    "- In welke maanden valt de meeste regen per stad?\n"
    "- Is er een visuele link tussen regenpieken en lagere Tmax?"
)

st.subheader("Bronnen")
st.markdown(
    "- [Open-Meteo Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)\n"
    "- [Streamlit Documentation](https://docs.streamlit.io/)"
)