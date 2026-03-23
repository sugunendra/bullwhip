import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

# ----------------------------
# Simulation Engine
# ----------------------------
class Stage:
    def __init__(self, delay, target_inventory, behavior_factor=1.0):
        self.delay = delay
        self.target_inventory = target_inventory
        self.behavior_factor = behavior_factor
        self.inventory = target_inventory
        self.backlog = 0
        self.pipeline = [0] * delay

    def step(self, incoming_order, manual_order=None):
        arriving = self.pipeline.pop(0)
        self.inventory += arriving

        fulfilled = min(self.inventory, incoming_order + self.backlog)

        self.inventory -= fulfilled
        self.backlog = incoming_order + self.backlog - fulfilled

        # If manual order provided (game mode), use it directly
        if manual_order is not None:
            order = int(manual_order)
        else:
            order = max((self.target_inventory - self.inventory + self.backlog) * self.behavior_factor, 0)
            order = int(round(order))

        self.pipeline.append(order)

        return {
            "order": order,
            "inventory": self.inventory,
            "backlog": self.backlog,
            "shipped": fulfilled,
            "on_order": sum(self.pipeline)
        }

# ----------------------------
# Demand Generator
# ----------------------------
def generate_demand(periods, mode):
    demand = []
    for t in range(periods):
        if mode == "Constant":
            demand.append(5)
        elif mode == "Random":
            demand.append(np.random.randint(3, 10))
        elif mode == "Seasonal":
            demand.append(int(5 + 3 * np.sin(2 * np.pi * t / 12)))
        elif mode == "Shock":
            base = 5
            shock = 15 if np.random.rand() < 0.1 else 0
            demand.append(base + shock)
    return demand

# ----------------------------
# Chart
# ----------------------------
def build_chart(df):
    base = alt.Chart(df).encode(x='Period')

    lines = base.transform_fold(
        ['Inventory', 'On Order', 'Shipped', 'Demand', 'Moving Avg Demand'],
        as_=['Metric', 'Value']
    ).mark_line().encode(
        y='Value:Q',
        color='Metric:N'
    )

    backlog = base.mark_rule(color='orange').transform_filter(
        alt.datum["Backlog Flag"] == True
    )

    return lines + backlog

# ----------------------------
# Replay Simulation
# ----------------------------
def replay_simulation(demand_series, delay, target_inventory, behavior, ma_window):
    stage = Stage(delay, target_inventory, behavior)

    data = []

    for t, d in enumerate(demand_series):
        r = stage.step(d)

        data.append({
            "Period": t,
            "Demand": d,
            "Inventory": r["inventory"],
            "On Order": r["on_order"],
            "Shipped": r["shipped"],
            "Backlog": r["backlog"]
        })

    df = pd.DataFrame(data)
    df["Moving Avg Demand"] = df["Demand"].rolling(window=ma_window, min_periods=1).mean()
    df["Backlog Flag"] = df["Backlog"] > 0

    return df

# ----------------------------
# UI
# ----------------------------
st.set_page_config(layout="wide")
st.title("Bullwhip Simulator")
st.text("For each period enter your order, considering the Demand, Inventory, Backlog and On order values. The order placed in current period will be delivered after the value of Lead time, set in setup parameter.")
# Sidebar (global params)
st.sidebar.header("Simulation Setup")

periods = st.sidebar.slider("Simulation periods", 20, 100, 60)
delay = st.sidebar.slider("Lead time", 1, 6, 2)
ma_window = st.sidebar.slider("Moving Average periods", 1, 20, 5)
demand_mode = st.sidebar.selectbox("Demand Type", ["Constant", "Random", "Seasonal", "Shock"])
target_inventory = st.sidebar.slider("Target Inventory  (System replay)", 5, 50, 20)
behavior = st.sidebar.slider("Behavior Amplification (System replay)", 0.5, 2.0, 1.0)

start_game = st.sidebar.button("Start New Simulation")

# ----------------------------
# Session State
# ----------------------------
if "initialized" not in st.session_state:
    st.session_state.initialized = False

if start_game:
    st.session_state.initialized = True
    st.session_state.demand_series = generate_demand(periods, demand_mode)
    st.session_state.stage = Stage(delay, target_inventory, behavior_factor=1.0)
    st.session_state.history = []
    st.session_state.t = 0

# ----------------------------
# Tabs
# ----------------------------
tab1, tab2 = st.tabs(["Play simulation", "System Replay"])

# ============================
# TAB 1: GAME
# ============================
with tab1:
    st.header("Play simulation")

    if not st.session_state.initialized:
        st.info("Set parameters and click 'Start New Simulation'")
    else:
        t = st.session_state.t
        demand_series = st.session_state.demand_series
        stage = st.session_state.stage

        if t >= len(demand_series):
            st.success("Simulation Finished")
        else:
            demand = demand_series[t]

            st.write(f"Period: {t}")
            st.write(f"Demand: {demand}")
            st.write(f"Inventory: {stage.inventory}")
            st.write(f"Backlog: {stage.backlog}")
            st.write(f"On Order: {sum(stage.pipeline)}")

            # Persist previous order value for better UX
            if "last_order" not in st.session_state:
                st.session_state.last_order = 5

            order = st.number_input(
                "Your Order",
                min_value=0,
                max_value=50,
                value=st.session_state.last_order,
                key="order_input"
            )

            if st.button("Submit Step"):
                # Save last entered order
                st.session_state.last_order = order
                r = stage.step(demand, manual_order=order)

                st.session_state.history.append({
                    "Period": t,
                    "Demand": demand,
                    "Inventory": r["inventory"],
                    "On Order": r["on_order"],
                    "Shipped": r["shipped"],
                    "Backlog": r["backlog"]
                })

                st.session_state.t += 1

        if len(st.session_state.history) > 1:
            df = pd.DataFrame(st.session_state.history)
            df["Moving Avg Demand"] = df["Demand"].rolling(window=ma_window, min_periods=1).mean()
            df["Backlog Flag"] = df["Backlog"] > 0

            st.subheader("Game Chart")
            st.altair_chart(build_chart(df), use_container_width=True)

# ============================
# TAB 2: SYSTEM REPLAY
# ============================
with tab2:
    st.header("Replay with System Policy")

    if not st.session_state.initialized or len(st.session_state.history) == 0:
        st.warning("Play the game first.")
    else:
        if st.button("Run System Simulation"):
            df = replay_simulation(
                st.session_state.demand_series[:len(st.session_state.history)],
                delay,
                target_inventory,
                behavior,
                ma_window
            )

            st.altair_chart(build_chart(df), use_container_width=True)
            st.dataframe(df)
