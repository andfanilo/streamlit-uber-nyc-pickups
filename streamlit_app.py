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


@st.cache_data
def filterdata(df, start_time, end_time):
    """Filter data between start and end time"""
    times = df["date/time"].dt.time
    if start_time <= end_time:
        return df[(times >= start_time) & (times < end_time)]
    # range crosses midnight
    return df[(times >= start_time) | (times < end_time)]


@st.cache_data
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


@st.cache_data
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


def add_minutes(t, minutes):
    """Shift a time-of-day by N minutes (wraps past midnight)"""
    return (datetime.combine(date.today(), t) + timedelta(minutes=minutes)).time()


DURATION_OPTIONS = {"15 min": 15, "30 min": 30, "1 hour": 60}

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
kpi_label = st.empty()
map_column, kpi_column = st.columns(
    (1.5, 1),
    gap="large",
)
st.space("small")


histogram_container = st.container(border=False, height=HISTOGRAM_HEIGHT)

###################################################
# APP
###################################################

data = load_data()
midpoint = (np.average(data["lat"]), np.average(data["lon"]))

with left_header:
    st.title("NYC Uber Ridesharing Data")

with right_header:
    st.space("small")
    st.markdown(
        """
        Explore Uber pickups across New York City throughout September 2014.
        Pick a start hour and a duration on the left. The map shows where pickups cluster, the card tracks
        rides per day in that window, and the chart below breaks the window down minute by minute.
        Click a hex to inspect a specific neighborhood.
        """
    )

with filters_container:
    start_col, end_col = st.columns(2, gap="large")
    with start_col:
        selected_start_hour = st.time_input(
            "Start hour",
            value=time(hour=0),
            key="start_hour",
            bind="query-params",
        )
    with end_col:
        selected_duration = st.pills(
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

with map_column:
    start_label = selected_start_hour.strftime("%H:%M")
    end_label = selected_end_hour.strftime("%H:%M")

    kpi_label.write(f"""**All New York City from {start_label} to {end_label}**""")
    map_state = render_map(
        hour_data, midpoint[0], midpoint[1], height=MAP_HEIGHT, key="nyc_map"
    )

with kpi_column:
    picked = (map_state.selection.objects or {}).get(HEX_LAYER_ID, [])
    with st.container(
        border=True,
        gap="medium",
        height="stretch",
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
            daily_counts(data, selected_start_hour, selected_end_hour),
            x="day",
            y="rides",
            color=CHART_COLOR,
            x_label="Day of September",
            y_label="Rides",
            height="stretch",
        )

chart_data = histdata(data, selected_start_hour, selected_end_hour)

with histogram_container:
    st.write(
        f"""**Breakdown of rides per minute between {start_label} and {end_label}**"""
    )
    st.altair_chart(
        alt.Chart(chart_data)
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
        height="stretch",
        width="stretch",
        theme="streamlit",
    )

st.stop()
st.space("small")
with st.expander("DEBUG", icon=":material/bug_report:"):
    st.dataframe(data)
    st.write(map_state.selection.objects)
    st.write(st.context.headers)
