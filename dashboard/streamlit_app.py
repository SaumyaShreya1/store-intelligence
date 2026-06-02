import streamlit as st
import requests
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

st.set_page_config(page_title="Store Intelligence", page_icon="🛍️", layout="wide")

API = "http://localhost:8000"
STORE = "STORE_PURPLLE_001"

st.title("🛍️ Store Intelligence Dashboard")
st.caption("Purplle Tech Challenge 2026 - Real-time Store Analytics")

def fetch(url):
    try:
        r = requests.get(url, timeout=5)
        return r.json()
    except:
        return None

metrics   = fetch(f"{API}/stores/{STORE}/metrics?window_minutes=999999")
funnel    = fetch(f"{API}/stores/{STORE}/funnel?window_minutes=999999")
heatmap   = fetch(f"{API}/stores/{STORE}/heatmap?window_minutes=999999")
anomalies = fetch(f"{API}/stores/{STORE}/anomalies")
health    = fetch(f"{API}/health")

st.subheader("📊 Key Metrics")
col1, col2, col3, col4, col5 = st.columns(5)
if metrics:
    col1.metric("Unique Visitors",  metrics.get("unique_visitors", 0))
    col2.metric("Conversion Rate",  f"{metrics.get(chr(99)+chr(111)+chr(110)+chr(118)+chr(101)+chr(114)+chr(115)+chr(105)+chr(111)+chr(110)+chr(95)+chr(114)+chr(97)+chr(116)+chr(101), 0)*100:.1f}%")
    col3.metric("Avg Dwell Time",   f"{metrics.get(chr(97)+chr(118)+chr(103)+chr(95)+chr(100)+chr(119)+chr(101)+chr(108)+chr(108)+chr(95)+chr(109)+chr(115), 0)/1000:.1f}s")
    col4.metric("Queue Depth",      metrics.get("queue_depth", 0))
    col5.metric("Abandonment Rate", f"{metrics.get(chr(97)+chr(98)+chr(97)+chr(110)+chr(100)+chr(111)+chr(110)+chr(109)+chr(101)+chr(110)+chr(116)+chr(95)+chr(114)+chr(97)+chr(116)+chr(101), 0)*100:.1f}%")
else:
    st.error("Cannot connect to API. Make sure it is running on port 8000.")

st.divider()
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🔥 Zone Heatmap")
    if heatmap and heatmap.get("zones"):
        df = pd.DataFrame(heatmap["zones"])
        fig = px.bar(
            df.sort_values("normalized_score", ascending=True),
            x="normalized_score", y="zone_id", orientation="h",
            color="normalized_score", color_continuous_scale="Reds",
            labels={"normalized_score": "Activity Score", "zone_id": "Zone"},
            title="Zone Activity Score 0 to 100")
        fig.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

        fig2 = px.bar(
            df.sort_values("avg_dwell_ms", ascending=True),
            x="avg_dwell_ms", y="zone_id", orientation="h",
            color="avg_dwell_ms", color_continuous_scale="Blues",
            labels={"avg_dwell_ms": "Avg Dwell ms", "zone_id": "Zone"},
            title="Average Dwell Time per Zone ms")
        fig2.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No heatmap data available")

with col_right:
    st.subheader("🎯 Conversion Funnel")
    if funnel and funnel.get("stages"):
        df2 = pd.DataFrame(funnel["stages"])
        fig3 = go.Figure(go.Funnel(
            y=df2["stage"], x=df2["count"],
            textinfo="value+percent initial",
            marker=dict(color=["#667eea","#764ba2","#f093fb","#f5576c"])))
        fig3.update_layout(title="Customer Conversion Funnel", height=350)
        st.plotly_chart(fig3, use_container_width=True)

        fig4 = px.bar(
            df2[df2["drop_off_pct"] > 0],
            x="stage", y="drop_off_pct",
            color="drop_off_pct", color_continuous_scale="Reds",
            labels={"drop_off_pct": "Drop-off %", "stage": "Stage"},
            title="Drop-off Percentage per Stage")
        fig4.update_layout(height=300)
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No funnel data available")

st.divider()
st.subheader("🚨 Active Anomalies")
if anomalies and anomalies.get("anomalies"):
    for a in anomalies["anomalies"]:
        sev = a.get("severity", "INFO")
        desc = a.get("description", "")
        atype = a.get("anomaly_type", "")
        action = a.get("suggested_action", "")
        if sev == "CRITICAL":
            st.error(f"🔴 {atype} — {desc} | Action: {action}")
        elif sev == "WARN":
            st.warning(f"🟡 {atype} — {desc} | Action: {action}")
        else:
            st.info(f"🔵 {atype} — {desc}")
else:
    st.success("✅ No active anomalies detected")

st.divider()
st.subheader("💚 API Health")
if health:
    status = health.get("status", "UNKNOWN")
    uptime = health.get("uptime_seconds", 0)
    checked = health.get("checked_at", "")
    if status == "OK":
        st.success(f"API Status: {status} | Uptime: {uptime:.0f}s | Checked: {checked}")
    else:
        st.error(f"API Status: {status}")
else:
    st.error("API unreachable")

st.caption("Press R to reload | Data from real Purplle store CCTV footage")

