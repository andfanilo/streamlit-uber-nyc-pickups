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


@st.cache_resource
def load_data():
    """Load data from zip into cache"""
    path = "uber-raw-data-sep14.csv.gz"
    if not os.path.isfile(path):
        path = f"https://github.com/streamlit/demo-uber-nyc-pickups/raw/main/{path}"

    data = pd.read_csv(
        path,
        nrows=100000,  # approx. 10% of data
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
    )

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
def mpoint(lat, lon):
    """Calculate midpoint for given set of data"""
    return (np.average(lat), np.average(lon))


@st.cache_data
def histdata(df, start_time, end_time):
    """Compute pickups per minute-of-hour within a time-of-day range"""
    filtered = filterdata(df, start_time, end_time)
    hist = np.histogram(filtered["date/time"].dt.minute, bins=60, range=(0, 60))[0]
    return pd.DataFrame({"minute": range(60), "pickups": hist})


def add_hour(t):
    """Add one hour to a date"""
    return (datetime.combine(date.today(), t) + timedelta(hours=1)).time()


###################################################
# VISUALIZATION
###################################################

MAP_STYLE = (
    "mapbox://styles/mapbox/dark-v10"
    if _IS_DARK
    else "mapbox://styles/mapbox/light-v10"
)
HEX_LAYER_ID = "hex"


def map(data, lat, lon, zoom, key=None):
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
        height=350,
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
map_column, kpi_column = st.columns(
    (1.5, 1),
    gap="large",
)
st.space("small")


histogram_container = st.container()

###################################################
# APP
###################################################

data = load_data()

with left_header:
    st.title("NYC Uber Ridesharing Data")

with right_header:
    st.space("small")
    st.markdown(
        """
        Examining how Uber pickups vary over time in New York City's and at its major regional airports.
        By sliding the slider on the left you can view different slices of time and explore different transportation trends.
        """
    )

with filters_container:
    start_col, end_col = st.columns(2)
    with start_col:
        selected_start_hour = st.time_input(
            "Start hour",
            value=time(hour=0),
            key="start_hour",
            bind="query-params",
        )
    with end_col:
        selected_end_hour = st.time_input(
            "End hour",
            value=None,
            key="end_hour",
            bind="query-params",
        )

if selected_end_hour is None:
    selected_end_hour = add_hour(selected_start_hour)

hour_data = filterdata(data, selected_start_hour, selected_end_hour)

with map_column:
    zoom_level = 11
    midpoint = mpoint(data["lat"], data["lon"])
    start_label = selected_start_hour.strftime("%H:%M")
    end_label = selected_end_hour.strftime("%H:%M")

    st.write(f"""**All New York City from {start_label} to {end_label}**""")
    map_state = map(hour_data, midpoint[0], midpoint[1], zoom_level, key="nyc_map")

with kpi_column:
    picked = (map_state.selection.objects or {}).get(HEX_LAYER_ID, [])
    if picked:
        obj = picked[0]
        rides_in_selection = obj.get("count")
        label = "Rides in selected hex"
    else:
        rides_in_selection = len(hour_data)
        label = f"Total rides {start_label}–{end_label}"

    st.markdown("")
    st.space("small")
    st.metric(label, f"{rides_in_selection:,}", border=True)

chart_data = histdata(data, selected_start_hour, selected_end_hour)

with histogram_container:
    st.write(
        f"""**Breakdown of rides per minute between {start_label} and {end_label}**"""
    )

    chart_color = "#FFFFFF" if _IS_DARK else "#000000"
    st.altair_chart(
        alt.Chart(chart_data)
        .mark_area(
            interpolate="step-after",
        )
        .encode(
            x=alt.X("minute:Q", scale=alt.Scale(nice=False)),
            y=alt.Y("pickups:Q"),
            tooltip=["minute", "pickups"],
        )
        .configure_mark(opacity=0.6, color=chart_color),
        width="stretch",
        theme="streamlit",
    )

st.space("small")
with st.expander("DEBUG", icon=":material/bug_report:"):
    st.dataframe(data)
    st.write(map_state.selection.objects)
    st.write(st.context.headers)
