"""
Restaurant Analytics Dashboard
CS5200 Practicum I, Part H -- Rituraj Singh, Fall 2026

A Streamlit web app that reports on the restaurant-visits database
hosted on Aiven MySQL. All aggregation is done in SQL on the live
database; the app only displays the (small) query results.

Built with the help of Claude (Anthropic) as the AI coding assistant.
"""

import pandas as pd
import plotly.express as px
import pymysql
import streamlit as st

st.set_page_config(page_title="Restaurant Analytics", page_icon="🍔", layout="wide")

CACHE_TTL = 600  # seconds; query results are reused for 10 minutes


# --------------------------------------------------------------------------
# Database access
# --------------------------------------------------------------------------

def get_connection():
    """Opens a connection to the Aiven MySQL database using Streamlit secrets.

    Aiven requires SSL. If a CA certificate is configured (ssl_ca), the
    server certificate is verified; otherwise the connection is still
    encrypted, but the certificate is not verified.
    """
    cfg = st.secrets["mysql"]
    ssl = {"ca": cfg["ssl_ca"]} if cfg.get("ssl_ca") else {"check_hostname": False}
    return pymysql.connect(
        host=cfg["host"],
        port=int(cfg["port"]),
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        ssl=ssl,
        connect_timeout=15,
    )


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def run_query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Runs a parameterized query and returns the result as a DataFrame.

    Parameters are always passed, so a literal % in SQL is written as %%.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
    finally:
        conn.close()
    df = pd.DataFrame(rows, columns=cols)
    # DECIMAL values arrive as Decimal objects; convert them to floats
    for c in df.columns:
        if df[c].dtype == object:
            try:
                df[c] = pd.to_numeric(df[c])
            except (ValueError, TypeError):
                pass
    return df


# Common FROM clause for visit-level queries
BASE_FROM = """
    FROM visits v
    JOIN restaurants r     ON r.restaurant_id      = v.restaurant_id
    JOIN meal_types mt     ON mt.meal_type_id      = v.meal_type_id
    JOIN payment_methods p ON p.payment_method_id  = v.payment_method_id
"""


def build_where(years, restaurant_ids, meal_types):
    """Builds the WHERE clause and parameters for the sidebar filters."""
    clauses = ["YEAR(v.visit_date) BETWEEN %s AND %s"]
    params = [years[0], years[1]]
    if restaurant_ids:
        clauses.append("v.restaurant_id IN (" + ",".join(["%s"] * len(restaurant_ids)) + ")")
        params.extend(restaurant_ids)
    if meal_types:
        clauses.append("mt.meal_type IN (" + ",".join(["%s"] * len(meal_types)) + ")")
        params.extend(meal_types)
    return "WHERE " + " AND ".join(clauses), tuple(params)


def money(x: float) -> str:
    return f"${x:,.0f}"


# --------------------------------------------------------------------------
# Sidebar filters
# --------------------------------------------------------------------------

try:
    bounds = run_query("SELECT MIN(YEAR(visit_date)) AS lo, MAX(YEAR(visit_date)) AS hi FROM visits")
    restaurants = run_query(
        "SELECT restaurant_id, restaurant_name, city, state FROM restaurants ORDER BY restaurant_name")
    meals = run_query("SELECT meal_type FROM meal_types ORDER BY meal_type_id")
except Exception as e:  # noqa: BLE001
    st.error("Could not connect to the database. If the Aiven service was powered off "
             "after inactivity, start it in the Aiven console and reload this page.")
    st.caption(f"Details: {e}")
    st.stop()

lo, hi = int(bounds.lo[0]), int(bounds.hi[0])

st.sidebar.title("Filters")
years = st.sidebar.slider("Years", lo, hi, (lo, hi))
name_to_id = dict(zip(restaurants.restaurant_name, restaurants.restaurant_id))
picked = st.sidebar.multiselect("Restaurants (all if empty)", list(name_to_id))
picked_meals = st.sidebar.multiselect("Meal types (all if empty)", list(meals.meal_type))
if st.sidebar.button("Refresh data"):
    st.cache_data.clear()
st.sidebar.caption(f"Data is cached for {CACHE_TTL // 60} minutes.")

WHERE, PARAMS = build_where(years, [int(name_to_id[n]) for n in picked], picked_meals)


# --------------------------------------------------------------------------
# Header and key figures
# --------------------------------------------------------------------------

st.title("🍔 Restaurant Analytics Dashboard")
st.caption("Live data from the CS5200 Practicum I database (Aiven MySQL)")

kpi = run_query(f"""
    SELECT COUNT(*)                                  AS visits,
           SUM(v.food_bill)                          AS food,
           SUM(v.alcohol_bill)                       AS alcohol,
           SUM(v.tip_amount)                         AS tips,
           COUNT(DISTINCT v.customer_id)             AS customers,
           AVG(v.customer_id IS NOT NULL)            AS loyalty_share,
           AVG(v.food_bill + v.alcohol_bill)         AS avg_check
    {BASE_FROM} {WHERE}""", PARAMS).iloc[0]

if kpi.visits == 0:
    st.warning("No visits match the selected filters.")
    st.stop()

row1 = st.columns(4)
row1[0].metric("Visits", f"{int(kpi.visits):,}")
row1[1].metric("Revenue (food + alcohol)", money(kpi.food + kpi.alcohol))
row1[2].metric("Food", money(kpi.food))
row1[3].metric("Alcohol", money(kpi.alcohol))

row2 = st.columns(4)
row2[0].metric("Tips", money(kpi.tips))
row2[1].metric("Unique loyalty customers", f"{int(kpi.customers):,}")
row2[2].metric("Avg. check", f"${kpi.avg_check:,.2f}")
row2[3].metric("Loyalty visits", f"{kpi.loyalty_share:.1%}")

tabs = st.tabs(["Restaurants", "Trends", "Food vs Alcohol", "Operations", "Servers"])


# --------------------------------------------------------------------------
# Tab 1: per restaurant
# --------------------------------------------------------------------------

with tabs[0]:
    per_rest = run_query(f"""
        SELECT r.restaurant_name                 AS restaurant,
               CONCAT(r.city, ', ', r.state)     AS location,
               COUNT(*)                          AS visits,
               SUM(v.food_bill)                  AS food,
               SUM(v.alcohol_bill)               AS alcohol,
               SUM(v.food_bill + v.alcohol_bill) AS revenue,
               SUM(v.tip_amount)                 AS tips,
               COUNT(DISTINCT v.customer_id)     AS unique_customers,
               AVG(v.party_size)                 AS avg_party,
               AVG(v.wait_time)                  AS avg_wait
        {BASE_FROM} {WHERE}
        GROUP BY r.restaurant_id, r.restaurant_name, r.city, r.state
        ORDER BY revenue DESC""", PARAMS)

    left, right = st.columns(2)
    left.plotly_chart(
        px.bar(per_rest.sort_values("visits"), x="visits", y="restaurant",
               orientation="h", title="Total visits per restaurant"),
        use_container_width=True)
    stacked = per_rest.melt(id_vars="restaurant", value_vars=["food", "alcohol"],
                            var_name="type", value_name="amount")
    right.plotly_chart(
        px.bar(stacked, x="amount", y="restaurant", color="type", orientation="h",
               title="Revenue per restaurant (food + alcohol)",
               category_orders={"restaurant": list(per_rest.restaurant[::-1])}),
        use_container_width=True)

    st.plotly_chart(
        px.bar(per_rest.sort_values("unique_customers", ascending=False),
               x="restaurant", y="unique_customers",
               title=f"Unique loyalty customers per restaurant "
                     f"(across all restaurants: {int(kpi.customers)})"),
        use_container_width=True)
    st.caption("A customer who visits several restaurants is counted once per restaurant, "
               "so the bars add up to more than the total across restaurants.")

    st.dataframe(
        per_rest.style.format({"food": "${:,.0f}", "alcohol": "${:,.0f}",
                               "revenue": "${:,.0f}", "tips": "${:,.0f}",
                               "visits": "{:,}", "avg_party": "{:.2f}",
                               "avg_wait": "{:.1f} min"}),
        use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------
# Tab 2: trends by month and year
# --------------------------------------------------------------------------

with tabs[1]:
    monthly = run_query(f"""
        SELECT DATE_FORMAT(v.visit_date, '%%Y-%%m-01') AS month,
               COUNT(*)                                AS visits,
               SUM(v.food_bill)                        AS food,
               SUM(v.alcohol_bill)                     AS alcohol,
               SUM(v.food_bill + v.alcohol_bill)       AS revenue
        {BASE_FROM} {WHERE}
        GROUP BY month ORDER BY month""", PARAMS)
    monthly["month"] = pd.to_datetime(monthly["month"])

    st.plotly_chart(px.line(monthly, x="month", y="revenue", markers=True,
                            title="Revenue per month"), use_container_width=True)
    st.plotly_chart(px.bar(monthly, x="month", y="visits",
                           title="Visits per month"), use_container_width=True)

    yearly = run_query(f"""
        SELECT YEAR(v.visit_date)                AS year,
               COUNT(*)                          AS visits,
               SUM(v.food_bill)                  AS food,
               SUM(v.alcohol_bill)               AS alcohol,
               SUM(v.food_bill + v.alcohol_bill) AS revenue,
               SUM(v.tip_amount)                 AS tips
        {BASE_FROM} {WHERE}
        GROUP BY year ORDER BY year""", PARAMS)
    left, right = st.columns([3, 2])
    left.plotly_chart(
        px.bar(yearly.melt(id_vars="year", value_vars=["food", "alcohol"],
                           var_name="type", value_name="amount"),
               x="year", y="amount", color="type", title="Revenue per year"),
        use_container_width=True)
    right.dataframe(
        yearly.style.format({"visits": "{:,}", "food": "${:,.0f}", "alcohol": "${:,.0f}",
                             "revenue": "${:,.0f}", "tips": "${:,.0f}"}),
        use_container_width=True, hide_index=True)


# --------------------------------------------------------------------------
# Tab 3: food vs alcohol
# --------------------------------------------------------------------------

with tabs[2]:
    left, right = st.columns(2)
    left.plotly_chart(
        px.pie(names=["Food", "Alcohol"], values=[kpi.food, kpi.alcohol], hole=0.45,
               title="Total spent on food vs alcohol"),
        use_container_width=True)

    by_meal = run_query(f"""
        SELECT mt.meal_type                AS meal_type,
               SUM(v.food_bill)            AS food,
               SUM(v.alcohol_bill)         AS alcohol,
               AVG(v.alcohol_bill > 0)     AS share_with_alcohol
        {BASE_FROM} {WHERE}
        GROUP BY mt.meal_type_id, mt.meal_type ORDER BY mt.meal_type_id""", PARAMS)
    right.plotly_chart(
        px.bar(by_meal.melt(id_vars="meal_type", value_vars=["food", "alcohol"],
                            var_name="type", value_name="amount"),
               x="meal_type", y="amount", color="type", barmode="group",
               title="Food vs alcohol by meal type"),
        use_container_width=True)

    alc_rest = run_query(f"""
        SELECT r.restaurant_name                                        AS restaurant,
               AVG(v.alcohol_bill > 0)                                  AS share_with_alcohol,
               SUM(v.alcohol_bill) / NULLIF(SUM(v.food_bill + v.alcohol_bill), 0)
                                                                        AS alcohol_share_of_revenue
        {BASE_FROM} {WHERE}
        GROUP BY r.restaurant_id, r.restaurant_name
        ORDER BY alcohol_share_of_revenue DESC""", PARAMS)
    fig = px.bar(alc_rest, x="restaurant", y="alcohol_share_of_revenue",
                 title="Alcohol as a share of revenue, per restaurant")
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)


# --------------------------------------------------------------------------
# Tab 4: operations
# --------------------------------------------------------------------------

with tabs[3]:
    left, right = st.columns(2)

    by_hour = run_query(f"""
        SELECT HOUR(v.visit_time) AS hour, COUNT(*) AS visits
        {BASE_FROM} {WHERE} AND v.visit_time IS NOT NULL
        GROUP BY hour ORDER BY hour""", PARAMS)
    left.plotly_chart(px.bar(by_hour, x="hour", y="visits",
                             title="Visits by hour of day (where time is recorded)"),
                      use_container_width=True)

    pay = run_query(f"""
        SELECT p.payment_method AS method, COUNT(*) AS visits
        {BASE_FROM} {WHERE}
        GROUP BY p.payment_method_id, p.payment_method""", PARAMS)
    right.plotly_chart(px.pie(pay, names="method", values="visits", hole=0.45,
                              title="Payment methods"), use_container_width=True)

    left, right = st.columns(2)
    wait = run_query(f"""
        SELECT mt.meal_type AS meal_type, AVG(v.wait_time) AS avg_wait
        {BASE_FROM} {WHERE}
        GROUP BY mt.meal_type_id, mt.meal_type ORDER BY mt.meal_type_id""", PARAMS)
    left.plotly_chart(px.bar(wait, x="meal_type", y="avg_wait",
                             title="Average wait time (minutes) by meal type"),
                      use_container_width=True)

    party = run_query(f"""
        SELECT v.party_size AS party_size, COUNT(*) AS visits
        {BASE_FROM} {WHERE} AND v.party_size IS NOT NULL
        GROUP BY v.party_size ORDER BY v.party_size""", PARAMS)
    right.plotly_chart(px.bar(party, x="party_size", y="visits",
                              title="Party size distribution"),
                       use_container_width=True)


# --------------------------------------------------------------------------
# Tab 5: servers
# --------------------------------------------------------------------------

with tabs[4]:
    servers = run_query(f"""
        SELECT CONCAT(s.first_name, ' ', s.last_name)  AS server,
               r.restaurant_name                       AS restaurant,
               COUNT(*)                                AS visits,
               SUM(v.food_bill + v.alcohol_bill)       AS revenue,
               SUM(v.tip_amount)                       AS tips,
               SUM(v.tip_amount) / NULLIF(SUM(v.food_bill + v.alcohol_bill), 0)
                                                       AS tip_rate
        {BASE_FROM}
        JOIN servers s ON s.emp_id = v.server_emp_id
        {WHERE}
        GROUP BY s.emp_id, s.first_name, s.last_name, r.restaurant_name
        ORDER BY revenue DESC""", PARAMS)

    no_server = run_query(f"""
        SELECT AVG(v.server_emp_id IS NULL) AS share {BASE_FROM} {WHERE}""", PARAMS).share[0]
    st.caption(f"{no_server:.1%} of the selected visits have no server recorded "
               "and are not included on this tab.")

    st.plotly_chart(px.bar(servers.head(15), x="server", y="revenue", color="restaurant",
                           title="Top 15 servers by revenue served"),
                    use_container_width=True)
    st.dataframe(
        servers.style.format({"visits": "{:,}", "revenue": "${:,.0f}",
                              "tips": "${:,.0f}", "tip_rate": "{:.1%}"}),
        use_container_width=True, hide_index=True)

st.divider()
st.caption("CS5200 Practicum I · Rituraj Singh · Fall 2026 · "
           "Built with Streamlit and Claude (Anthropic) as AI coding assistant")
