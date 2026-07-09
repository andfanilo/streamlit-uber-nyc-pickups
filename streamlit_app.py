import os
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

###################################################
# PAGE CONFIG
###################################################

st.set_page_config(
    layout="wide",
    page_title="NYC Ridesharing Demo",
    page_icon=":taxi:",
)

# THEME-AWARE STYLING: pick map + chart colors based on the active Streamlit theme
_IS_DARK = st.context.theme.type == "dark"

st.html("./styles.css")

###################################################
# DATA
###################################################


@st.cache_data
def load_data():
    """Load data from zip into cache"""
    path = "uber-raw-data-sep14.csv.gz"
    if not os.path.isfile(path):
        path = f"https://github.com/streamlit/demo-uber-nyc-pickups/raw/main/{path}"

    data = pd.read_csv(
        path,
        # nrows=100000,  # approx. 10% of data
        names=[
            "date/time",
            "lat",
            "lon",
        ],  # specify names directly since they don't change
        skiprows=1,  # don't read header since names specified directly
        usecols=[0, 1, 2],  # doesn't load last column, constant value "B02512"
        parse_dates=[
            "date/time"
        ],  # set as datetime instead of converting after the fact
    ).sample(100000, random_state=42)

    return data


# Derived caches are keyed per (start, end) window; max_entries keeps them
# from growing unbounded as users explore filter combinations.
@st.cache_data(max_entries=32)
def filterdata(df, start_time, end_time):
    """Filter data between start and end time"""
    times = df["date/time"].dt.time
    if start_time <= end_time:
        return df[(times >= start_time) & (times < end_time)]
    # range crosses midnight
    return df[(times >= start_time) | (times < end_time)]


@st.cache_data(max_entries=64)
def histdata(df, start_time, end_time):
    """Pickups per minute-of-window, indexed 0..duration-1 from start_time"""
    filtered = filterdata(df, start_time, end_time)
    start_min = start_time.hour * 60 + start_time.minute
    end_min = end_time.hour * 60 + end_time.minute
    duration = (end_min - start_min) % (24 * 60) or 24 * 60
    ride_min = filtered["date/time"].dt.hour * 60 + filtered["date/time"].dt.minute
    offset = (ride_min - start_min) % (24 * 60)
    hist = np.histogram(offset, bins=duration, range=(0, duration))[0]
    return pd.DataFrame({"minute": range(duration), "pickups": hist})


@st.cache_data(max_entries=64)
def daily_counts(df, start_time, end_time):
    """Rides per calendar day within a time-of-day window"""
    filtered = filterdata(df, start_time, end_time)
    all_days = pd.date_range(
        df["date/time"].min().normalize(),
        df["date/time"].max().normalize(),
        freq="D",
    )
    counts = filtered.groupby(filtered["date/time"].dt.normalize()).size()
    counts = counts.reindex(all_days, fill_value=0)
    return pd.DataFrame({"day": counts.index.day, "rides": counts.values})


# Rough NYC borough bounding boxes (not official boundaries) used to bucket
# pickups by lat/lon for a quick borough-level breakdown.
@st.cache_data(max_entries=64)
def borough_counts(df, start_time, end_time):
    """Rides per rough NYC borough within a time-of-day window"""
    filtered = filterdata(df, start_time, end_time)
    lat, lon = filtered["lat"], filtered["lon"]
    conditions = [
        (lat >= 40.699) & (lat <= 40.882) & (lon >= -74.019) & (lon <= -73.907),
        (lat >= 40.785) & (lon >= -73.933) & (lon <= -73.765),
        lon <= -74.05,
        (lat >= 40.700) & (lon > -73.962) & (lon <= -73.70),
        (lat >= 40.570) & (lat < 40.739) & (lon >= -74.05) & (lon <= -73.83),
    ]
    choices = ["Manhattan", "Bronx", "Staten Island", "Queens", "Brooklyn"]
    borough = np.select(conditions, choices, default="Other")
    counts = (
        pd.Series(borough, name="borough")
        .value_counts()
        .rename_axis("borough")
        .reset_index(name="rides")
        .sort_values("rides", ascending=False)
    )
    return counts


@st.cache_data
def hourly_weekday_counts(df):
    """Pickups by hour-of-day x day-of-week, across the full dataset"""
    d = df.assign(
        hour=df["date/time"].dt.hour,
        weekday=df["date/time"].dt.day_name(),
    )
    return d.groupby(["weekday", "hour"]).size().reset_index(name="rides")


@st.cache_data(max_entries=64)
def gap_data(df, start_time, end_time):
    """Seconds between consecutive pickups within a time-of-day window"""
    filtered = filterdata(df, start_time, end_time).sort_values("date/time")
    gaps = filtered["date/time"].diff().dt.total_seconds().dropna()
    gaps = gaps[(gaps > 0) & (gaps < 600)]  # drop cross-day jumps / outliers
    return pd.DataFrame({"gap_seconds": gaps})


def add_minutes(t, minutes):
    """Shift a time-of-day by N minutes (wraps past midnight)"""
    return (datetime.combine(date.today(), t) + timedelta(minutes=minutes)).time()


DURATION_OPTIONS = {"15 min": 15, "30 min": 30, "1 hour": 60}
WEEKDAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

###################################################
# VISUALIZATION
###################################################

MAP_STYLE = (
    "mapbox://styles/mapbox/dark-v10"
    if _IS_DARK
    else "mapbox://styles/mapbox/light-v10"
)
CHART_COLOR = "#FFFFFF" if _IS_DARK else "#000000"
HEX_LAYER_ID = "hex"

MAP_HEIGHT = 450
HISTOGRAM_HEIGHT = 300


def render_map(data, lat, lon, zoom=11, height=350, key=None):
    return st.pydeck_chart(
        pdk.Deck(
            layers=[
                pdk.Layer(
                    "HexagonLayer",
                    id=HEX_LAYER_ID,
                    data=data,
                    get_position=["lon", "lat"],
                    radius=100,
                    elevation_scale=4,
                    elevation_range=[0, 1000],
                    pickable=True,
                    extruded=True,
                    auto_highlight=True,
                ),
            ],
            api_keys={"mapbox": st.secrets["MAPBOX_API_KEY"]},
            map_provider="mapbox",
            map_style=MAP_STYLE,
            initial_view_state={
                "latitude": lat,
                "longitude": lon,
                "zoom": zoom,
                "pitch": 50,
            },
            tooltip={
                "html": "<span class='hex-tip' data-count='{elevationValue}'>{elevationValue} ride<span class='plural'>s</span></span>",
            },
        ),
        on_select="rerun",
        selection_mode="single-object",
        height=height,
        key=key,
    )


EXTRA_CHART_HEIGHT = 260


@st.fragment(parallel=True)
def render_map_fragment(hour_data, lat, lon):
    """Pickup map; propagates hex selection changes to the rest of the app"""
    map_state = render_map(hour_data, lat, lon, height=MAP_HEIGHT, key="nyc_map")
    picked = (map_state.selection.objects or {}).get(HEX_LAYER_ID, [])
    hex_count = picked[0].get("count") if picked else None
    # A hex click only reruns this fragment; trigger a full rerun so the KPI
    # fragment (in another column) picks up the new selection.
    if st.session_state.get("picked_hex_count") != hex_count:
        st.session_state.picked_hex_count = hex_count
        st.rerun(scope="app")


@st.fragment(parallel=True)
def render_kpi_fragment(data, hour_data, start_time, end_time, start_label, end_label):
    """Ride-count metric (whole window or selected hex) plus rides per day"""
    map_sel = st.session_state.get("nyc_map")
    picked = (
        (map_sel.selection.objects or {}).get(HEX_LAYER_ID, []) if map_sel else []
    )
    # Explicit height: "stretch" collapses inside the fragment's auto-height
    # wrapper container; match the map so the row lines up.
    with st.container(
        border=True,
        gap="medium",
        height=MAP_HEIGHT,
        key="kpi_container",
    ):
        if picked:
            hex_count = picked[0].get("count") or 0
            window_total = len(hour_data)
            share_pct = hex_count / window_total * 100 if window_total else 0
            st.metric(
                f"Rides in selected hex from {start_label} to {end_label}",
                f"{hex_count:,}",
                delta=f"{share_pct:.1f}% of rides in window",
                delta_color="off",
                delta_arrow="off",
                border=False,
            )
        else:
            total_in_window = len(hour_data)
            share_pct = total_in_window / len(data) * 100 if len(data) else 0
            st.metric(
                f"Total rides from {start_label} to {end_label}",
                f"{total_in_window:,}",
                delta=f"{share_pct:.1f}% of September rides",
                delta_color="off",
                delta_arrow="off",
                border=False,
            )

        st.bar_chart(
            daily_counts(data, start_time, end_time),
            x="day",
            y="rides",
            color=CHART_COLOR,
            x_label="Day of September",
            y_label="Rides",
            height="stretch",
        )


@st.fragment(parallel=True)
def render_minute_fragment(data, start_time, end_time, start_label, end_label):
    """Minute-by-minute breakdown of pickups within the selected window"""
    st.write(
        f"""**Breakdown of rides per minute between {start_label} and {end_label}**"""
    )
    st.altair_chart(
        alt.Chart(histdata(data, start_time, end_time))
        .mark_area(interpolate="monotone", color=CHART_COLOR, opacity=0.85)
        .encode(
            x=alt.X(
                "minute:Q",
                scale=alt.Scale(nice=False),
                title=f"Minute from {start_label}",
            ),
            y=alt.Y("pickups:Q", title="Pickups"),
            tooltip=["minute", "pickups"],
        ),
        # Explicit height: "stretch" collapses inside the fragment's
        # auto-height wrapper container; leave room for the header above.
        height=HISTOGRAM_HEIGHT - 60,
        width="stretch",
        theme="streamlit",
    )


def highlight_segments(start_time, end_time):
    """Hour-of-day span(s) covering the selected window, as (start, end) floats"""
    start_h = start_time.hour + start_time.minute / 60
    end_h = end_time.hour + end_time.minute / 60
    if start_h <= end_h:
        return [(start_h, end_h)]
    return [(start_h, 24.0), (0.0, end_h)]  # window wraps past midnight


@st.fragment(parallel=True)
def render_borough_fragment(data, start_time, end_time, start_label, end_label):
    """Rides per rough NYC borough, fully scoped to the selected window"""
    st.write(f"**Rides by borough from {start_label} to {end_label}**")
    st.altair_chart(
        alt.Chart(borough_counts(data, start_time, end_time))
        .mark_bar(color=CHART_COLOR, opacity=0.85)
        .encode(
            x=alt.X("borough:N", sort="-y", title="Borough"),
            y=alt.Y("rides:Q", title="Rides"),
            tooltip=["borough", "rides"],
        ),
        height=EXTRA_CHART_HEIGHT,
        width="stretch",
        theme="streamlit",
        key="borough_chart",
    )


@st.fragment(parallel=True)
def render_heatmap_fragment(data, start_time, end_time):
    """Hour x weekday heatmap across all data, with the selected window boxed"""
    st.write("**Rides by hour & weekday (selected window boxed)**")
    heat = hourly_weekday_counts(data).assign(hour_end=lambda d: d["hour"] + 1)
    highlight = pd.DataFrame(
        highlight_segments(start_time, end_time), columns=["hour_start", "hour_end"]
    )

    base = alt.Chart(heat).mark_rect().encode(
        x=alt.X(
            "hour:Q", title="Hour of day", scale=alt.Scale(domain=[0, 24], nice=False)
        ),
        x2="hour_end:Q",
        y=alt.Y("weekday:N", sort=WEEKDAY_ORDER, title=None),
        color=alt.Color(
            "rides:Q",
            title="Rides",
            scale=alt.Scale(scheme="greys", reverse=_IS_DARK),
        ),
        tooltip=["weekday", "hour", "rides"],
    )
    box = (
        alt.Chart(highlight)
        .mark_rect(fill=None, stroke=CHART_COLOR, strokeWidth=2)
        .encode(x=alt.X("hour_start:Q"), x2="hour_end:Q")
    )

    st.altair_chart(
        base + box,
        height=EXTRA_CHART_HEIGHT,
        width="stretch",
        theme="streamlit",
        key="heatmap_chart",
    )


@st.fragment(parallel=True)
def render_gap_fragment(data, start_time, end_time, start_label, end_label):
    """Distribution of seconds between consecutive pickups in the selected window"""
    st.write(f"**Time between pickups from {start_label} to {end_label}**")
    st.altair_chart(
        alt.Chart(gap_data(data, start_time, end_time))
        .mark_bar(color=CHART_COLOR, opacity=0.85)
        .encode(
            x=alt.X(
                "gap_seconds:Q",
                bin=alt.Bin(maxbins=40),
                title="Seconds since previous pickup",
            ),
            y=alt.Y("count():Q", title="Occurrences"),
            tooltip=[alt.Tooltip("count()", title="Occurrences")],
        ),
        height=EXTRA_CHART_HEIGHT,
        width="stretch",
        theme="streamlit",
        key="gap_chart",
    )


###################################################
# LAYOUT
###################################################

# Title + Description
left_header, right_header = st.columns(
    (1.5, 1),
    gap="large",
)

# Hour filters
filters_container, _ = st.columns(
    (1.5, 1),
    gap="large",
)
st.space("small")

# Map + KPIs
kpi_label = st.container()
map_column, kpi_column = st.columns(
    (1.5, 1),
    gap="large",
)
st.space("small")

# Three parallel-loading fragments (st.fragment(parallel=True))
borough_col, heatmap_col, gap_col = st.columns(3, gap="large")
st.space("small")

histogram_container = st.container(border=False, height=HISTOGRAM_HEIGHT)

###################################################
# APP
###################################################

data = load_data()
midpoint = (np.average(data["lat"]), np.average(data["lon"]))

# Channel between the map fragment and the KPI fragment: the map stores the
# selected hex count here and triggers a full rerun when it changes.
st.session_state.setdefault("picked_hex_count", None)

left_header.title("NYC Uber Ridesharing Data")

right_header.space("small")
right_header.markdown(
    """
    Explore Uber pickups across New York City throughout September 2014.
    Pick a start hour and a duration on the left. The map shows where pickups cluster, the card tracks
    rides per day in that window, and the chart below breaks the window down minute by minute.
    Click a hex to inspect a specific neighborhood.
    """
)

start_col, end_col = filters_container.columns(2, gap="large")
selected_start_hour = start_col.time_input(
    "Start hour",
    value=time(hour=0),
    key="start_hour",
    bind="query-params",
)
selected_duration = end_col.segmented_control(
    "Duration",
    options=list(DURATION_OPTIONS),
    default="1 hour",
    key="duration",
    bind="query-params",
)
selected_end_hour = add_minutes(
    selected_start_hour, DURATION_OPTIONS[selected_duration]
)

hour_data = filterdata(data, selected_start_hour, selected_end_hour)

start_label = selected_start_hour.strftime("%H:%M")
end_label = selected_end_hour.strftime("%H:%M")

kpi_label.write(f"""**All New York City from {start_label} to {end_label}**""")

with map_column:
    render_map_fragment(hour_data, midpoint[0], midpoint[1])

with kpi_column:
    render_kpi_fragment(
        data,
        hour_data,
        selected_start_hour,
        selected_end_hour,
        start_label,
        end_label,
    )

with borough_col:
    render_borough_fragment(
        data, selected_start_hour, selected_end_hour, start_label, end_label
    )

with heatmap_col:
    render_heatmap_fragment(data, selected_start_hour, selected_end_hour)

with gap_col:
    render_gap_fragment(
        data, selected_start_hour, selected_end_hour, start_label, end_label
    )

with histogram_container:
    render_minute_fragment(
        data, selected_start_hour, selected_end_hour, start_label, end_label
    )
