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
# Adaptive Policy (NEW)
# ----------------------------
def adaptive_order(stage, demand_history, delay, alpha=0.5, safety_factor=1.0, prev_order=0):
    avg = np.mean(demand_history)
    std = np.std(demand_history) if len(demand_history) > 1 else 0

    target = avg * (delay + 1) + safety_factor * std

    raw_order = max(target - stage.inventory + stage.backlog, 0)

    order = alpha * raw_order + (1 - alpha) * prev_order

    return int(round(order))

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
# Cost Calculation
# ----------------------------
def calculate_costs(df, ordering_cost, holding_cost, goods_cost):
    num_orders = (df["Order"] > 0).sum()
    ordering_total = num_orders * ordering_cost

    holding_total = df["Inventory"].sum() * holding_cost

    avg_goods_cost = (df["Inventory"].sum() * goods_cost) / len(df)

    final_inventory_cost = df["Inventory"].iloc[-1] * goods_cost

    return {
        "Ordering Cost": ordering_total,
        "Holding Cost": holding_total,
        "Avg Goods Cost/Period": avg_goods_cost,
        "Final Inventory Cost": final_inventory_cost
    }

# ----------------------------
# Replay Simulation (UPDATED)
# ----------------------------
def replay_simulation(demand_series, delay, target_inventory, behavior, ma_window, mode):
    stage = Stage(delay, target_inventory, behavior)

    data = []
    demand_history = []
    prev_order = 0

    for t, d in enumerate(demand_series):

        demand_history.append(d)

        if mode == "Policy":
            r = stage.step(d)

        elif mode == "Adaptive Optimal":
            order = adaptive_order(stage, demand_history, delay, prev_order=prev_order)
            r = stage.step(d, manual_order=order)
            prev_order = order

        data.append({
            "Period": t,
            "Demand": d,
            "Inventory": r["inventory"],
            "On Order": r["on_order"],
            "Shipped": r["shipped"],
            "Backlog": r["backlog"],
            "Order": r["order"]
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

st.sidebar.header("Simulation Setup")
st.sidebar.text("For each period enter your order, considering the Demand, Inventory, Backlog and On order values. \nThe order placed in current period will be delivered after the value of Lead time, set in setup parameter. \nA Cost mode is availabel to assess the impact in cost terms.\n")


periods = st.sidebar.slider("Simulation periods", 10, 100, 30)
delay = st.sidebar.slider("Lead time", 1, 10, 2)
ma_window = st.sidebar.slider("Moving Average periods", 1, 20, 5)
demand_mode = st.sidebar.selectbox("Demand Type", ["Constant", "Random", "Seasonal", "Shock"])

target_inventory = st.sidebar.slider("Target Inventory (System)", 5, 50, 20)
behavior = st.sidebar.slider("Behavior Amplification (System)", 0.5, 2.0, 1.0)

policy_mode = st.sidebar.selectbox(
    "System Mode",
    ["Policy", "Adaptive Optimal"]
)

# Cost Mode
cost_mode = st.sidebar.toggle("Enable Cost Mode")

if cost_mode:
    ordering_cost = st.sidebar.number_input("Cost per Order", 0.0, value=10.0)
    holding_cost = st.sidebar.number_input("Holding Cost per Unit per Period", 0.0, value=5.0)
    goods_cost = st.sidebar.number_input("Cost of Goods per Unit", 0.0, value=50.0)

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

# ----------------------------
# TAB 1
# ----------------------------
with tab1:
    if not st.session_state.initialized:
        st.info("Start simulation from sidebar")
    else:
        t = st.session_state.t
        stage = st.session_state.stage
        demand_series = st.session_state.demand_series

        if t >= len(demand_series):
            st.success("Simulation Finished")
        else:
            demand = demand_series[t]

            st.write(f"Period: {t}")
            st.write(f"Demand: {demand}")
            st.write(f"Inventory: {stage.inventory}")
            st.write(f"Backlog: {stage.backlog}")
            st.write(f"On Order: {sum(stage.pipeline)}")

            if "last_order" not in st.session_state:
                st.session_state.last_order = 5

            order = st.number_input("Your Order", 0, 50, st.session_state.last_order)

            if st.button("Submit Step"):
                st.session_state.last_order = order
                r = stage.step(demand, manual_order=order)

                st.session_state.history.append({
                    "Period": t,
                    "Demand": demand,
                    "Inventory": r["inventory"],
                    "On Order": r["on_order"],
                    "Shipped": r["shipped"],
                    "Backlog": r["backlog"],
                    "Order": order
                })

                st.session_state.t += 1

        if len(st.session_state.history) > 1:
            df = pd.DataFrame(st.session_state.history)
            df["Moving Avg Demand"] = df["Demand"].rolling(window=ma_window, min_periods=1).mean()
            df["Backlog Flag"] = df["Backlog"] > 0

            st.altair_chart(build_chart(df), use_container_width=True)

            if cost_mode and t >= len(demand_series):
                costs = calculate_costs(df, ordering_cost, holding_cost, goods_cost)
                st.subheader("Cost Summary")
                for k, v in costs.items():
                    st.metric(k, round(v, 2))

# ----------------------------
# TAB 2
# ----------------------------
with tab2:
    if not st.session_state.initialized or len(st.session_state.history) == 0:
        st.warning("Play game first")
    else:
        if st.button("Run System Simulation"):
            df = replay_simulation(
                st.session_state.demand_series[:len(st.session_state.history)],
                delay,
                target_inventory,
                behavior,
                ma_window,
                policy_mode
            )

            st.altair_chart(build_chart(df), use_container_width=True)
            st.dataframe(df)

            if cost_mode:
                costs = calculate_costs(df, ordering_cost, holding_cost, goods_cost)
                st.subheader("System Cost Summary")
                for k, v in costs.items():
                    st.metric(k, round(v, 2))
