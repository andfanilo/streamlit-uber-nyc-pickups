import os

import altair as alt
import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

# SETTING PAGE CONFIG TO WIDE MODE AND ADDING A TITLE AND FAVICON
st.set_page_config(layout="wide", page_title="NYC Ridesharing Demo", page_icon=":taxi:")

# THEME-AWARE STYLING: pick map + chart colors based on the active Streamlit theme
_IS_DARK = st.context.theme.type == "dark"
MAP_STYLE = (
    "mapbox://styles/mapbox/dark-v10" if _IS_DARK else "mapbox://styles/mapbox/light-v10"
)


# LOAD DATA ONCE
@st.cache_resource
def load_data():
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

HEX_LAYER_ID = "hex"

def map(data, lat, lon, zoom, key=None):
    return st.pydeck_chart(
        pdk.Deck(
            map_style=MAP_STYLE,
            initial_view_state={
                "latitude": lat,
                "longitude": lon,
                "zoom": zoom,
                "pitch": 50,
            },
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
            tooltip={"text": "{elevationValue} rides"},
        ),
        on_select="rerun",
        selection_mode="single-object",
        key=key,
    )


# FILTER DATA FOR A SPECIFIC HOUR, CACHE
@st.cache_data
def filterdata(df, hour_selected):
    return df[df["date/time"].dt.hour == hour_selected]


# CALCULATE MIDPOINT FOR GIVEN SET OF DATA
@st.cache_data
def mpoint(lat, lon):
    return (np.average(lat), np.average(lon))


# FILTER DATA BY HOUR
@st.cache_data
def histdata(df, hr):
    filtered = data[
        (df["date/time"].dt.hour >= hr) & (df["date/time"].dt.hour < (hr + 1))
    ]

    hist = np.histogram(filtered["date/time"].dt.minute, bins=60, range=(0, 60))[0]

    return pd.DataFrame({"minute": range(60), "pickups": hist})


# STREAMLIT APP LAYOUT
data = load_data()

# LAYING OUT THE TOP SECTION OF THE APP
row1_1, row1_2 = st.columns((2, 3))

# SEE IF THERE'S A QUERY PARAM IN THE URL (e.g. ?pickup_hour=2)
# THIS ALLOWS YOU TO PASS A STATEFUL URL TO SOMEONE WITH A SPECIFIC HOUR SELECTED,
# E.G. https://share.streamlit.io/streamlit/demo-uber-nyc-pickups/main?pickup_hour=2
if not st.session_state.get("url_synced", False):
    try:
        pickup_hour = int(st.query_params["pickup_hour"])
        st.session_state["pickup_hour"] = pickup_hour
        st.session_state["url_synced"] = True
    except KeyError:
        pass


# IF THE SLIDER CHANGES, UPDATE THE QUERY PARAM
def update_query_params():
    hour_selected = st.session_state["pickup_hour"]
    st.query_params["pickup_hour"] = hour_selected


with row1_1:
    st.title("NYC Uber Ridesharing Data")
    hour_selected = st.slider(
        "Select hour of pickup", 0, 23, key="pickup_hour", on_change=update_query_params
    )


with row1_2:
    st.write(
        """
    ##
    Examining how Uber pickups vary over time in New York City's and at its major regional airports.
    By sliding the slider on the left you can view different slices of time and explore different transportation trends.
    """
    )

# LAYING OUT THE MIDDLE SECTION OF THE APP WITH THE MAPS
row2_1, row2_2 = st.columns((1.5, 1))

# SETTING THE ZOOM LOCATIONS FOR THE AIRPORTS
zoom_level = 12
midpoint = mpoint(data["lat"], data["lon"])

hour_data = filterdata(data, hour_selected)

with row2_1:
    st.write(
        f"""**All New York City from {hour_selected}:00 and {(hour_selected + 1) % 24}:00**"""
    )
    map_state = map(hour_data, midpoint[0], midpoint[1], 11, key="nyc_map")

with row2_2:
    picked = (map_state.selection.objects or {}).get(HEX_LAYER_ID, [])
    if picked:
        obj = picked[0]
        rides_in_selection = (
            len(obj.get("points") or [])
            or obj.get("count")
            or obj.get("elevationValue")
            or obj.get("colorValue")
            or 0
        )
        label = "Rides in selected hex"
    else:
        rides_in_selection = len(hour_data)
        label = f"Total rides {hour_selected:02d}:00–{(hour_selected + 1) % 24:02d}:00"
    st.metric(label, f"{rides_in_selection:,}")
    with st.expander("Debug: picked object"):
        st.write(picked)

# CALCULATING DATA FOR THE HISTOGRAM
chart_data = histdata(data, hour_selected)

# LAYING OUT THE HISTOGRAM SECTION
st.write(
    f"""**Breakdown of rides per minute between {hour_selected}:00 and {(hour_selected + 1) % 24}:00**"""
)

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
    .configure_mark(opacity=0.6, color="blue"),
    width="stretch",
)

st.dataframe(data)