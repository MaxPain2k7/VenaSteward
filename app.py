# VenaSteward dashboard - Mahir Jain, SSETC Hackathon 2026
# live demo: https://venasteward.streamlit.app
#
# to run it on your own computer
# install once:  python -m pip install -r requirements.txt
# run:           python -m streamlit run app.py
#
# data: morning_list.csv is made by analysis.ipynb from the MIMIC-IV Clinical Database Demo v2.2
# (PhysioNet). Shared under the Open Database License v1.0, same as the source.

from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

HERE = Path(__file__).parent
REVIEWS = HERE / "reviews.csv"
COLUMNS = ["day", "bed", "line_id", "reasons", "reason_status", "decision", "note",
           "senior_review", "reviewer", "time"]

REASONS = ["Blood pressure drugs", "TPN / IV nutrition", "Other essential drip",
           "Difficult veins", "Pressure monitoring", "Other"]
WEAK = ["Blood sampling only", "Convenience"]

st.set_page_config(page_title="VenaSteward", layout="wide")
plt.rcParams["font.family"] = "serif"
data = pd.read_csv(HERE / "morning_list.csv")


def status(row):
    if row.flag:
        return f"REVIEW - no reason for {row.idle_hours} h"
    if row.reasons:
        return "In use - " + row.reasons.lower()
    return f"Watch - reason ended {row.idle_hours} h ago"


def load_reviews():
    if REVIEWS.exists():
        return pd.read_csv(REVIEWS).fillna("")
    return pd.DataFrame(columns=COLUMNS)


def save_review(review, message, kind="success"):
    log = pd.concat([load_reviews(), pd.DataFrame([review])])
    log.to_csv(REVIEWS, index=False)
    st.session_state.message = (kind, message)
    st.rerun()  # so the morning list shows the new decision straight away


# ---------- sidebar ----------
st.sidebar.title("VenaSteward")
st.sidebar.write("Central line review for the ICU morning round")
day = st.sidebar.slider("Day (08:00 round)", 1, int(data.day.max()), 7)
reviewer = st.sidebar.text_input("Your name", "Dr A. Rao")
st.sidebar.markdown("**How to use:** pick a day, open **Line review**, choose a line and record a decision.")
st.sidebar.markdown("**Prototype only.** It never tells anyone to remove a line. The doctor decides.")
st.sidebar.caption("Real ICU stays from the open MIMIC-IV demo (100 US patients), replayed as a 12-bed unit. "
                   "Beds and day numbers are made up. Each morning only uses data from before 08:00.")
if st.sidebar.button("Clear review log"):
    REVIEWS.unlink(missing_ok=True)

reviews = load_reviews()
today = data[data.day == day].fillna({"reasons": "", "exposure": "", "forecast": "-"}).copy()
today["status"] = today.apply(status, axis=1)
latest = reviews[reviews.day == day].drop_duplicates("line_id", keep="last").set_index("line_id")
today["decision"] = [f"{latest.decision[l]} ({latest.reviewer[l]})" if l in latest.index else "Not reviewed"
                     for l in today.line_id]
today = today.sort_values(["flag", "idle_hours"], ascending=False)

tab1, tab2 = st.tabs(["Morning list", "Line review"])

# ---------- tab 1: morning list ----------
with tab1:
    st.header(f"Day {day} - central lines at 08:00")
    a, b, c = st.columns(3)
    a.metric("Lines in", len(today))
    b.metric("Flagged, still need a decision", int((today.flag & (today.decision == "Not reviewed")).sum()))
    c.metric("Reviewed today", len(latest))

    if today.empty:
        st.info("No central lines in on this day.")
    else:
        st.dataframe(
            today.assign(where=today.type + ", " + today.site)[
                ["bed", "line_id", "where", "line_day", "status", "decision", "forecast", "n_exposure"]].rename(columns={
                "bed": "Bed", "line_id": "Line", "where": "Type and site", "line_day": "Line day",
                "status": "Status", "decision": "Decision today", "forecast": "Forecast*",
                "n_exposure": "Risk**"}),
            hide_index=True, height=35 * (len(today) + 1) + 3,
        )
        st.caption("Flagged lines come first. A flag means no tracked reason (blood pressure drugs or TPN) for "
                   "24 hours. The record can't see every reason, like difficult veins, so the app asks for one "
                   "instead of giving an order. *Forecast (experimental) = will blood pressure support end by tomorrow's round. "
                   "**Risk = number of infection exposure factors (femoral site, TPN, more than one line).")

# ---------- tab 2: one line ----------
with tab2:
    if today.empty:
        st.info("No central lines in on this day.")
    else:
        names = {r.line_id: f"Bed {r.bed} - {r.line_id} - {r.status}" for r in today.itertuples()}
        pick = st.selectbox("Line", list(names), format_func=names.get)
        row = today[today.line_id == pick].iloc[0]
        new_line = row.line_day < 1
        left, right = st.columns([3, 2])

        with left:
            st.subheader(f"Bed {row.bed} - {row.type}, {row.site}")
            st.write(f"Line day **{row.line_day}** | ICU day **{row.icu_day}** | "
                     f"Hours without a reason **{row.idle_hours}**")
            if row.flag:
                st.error(f"No tracked reason for {row.idle_hours} hours. Is this line still needed?")
            elif row.reasons:
                st.success(f"In use: {row.reasons}")
            else:
                st.info(f"Reason ended {row.idle_hours} hours ago. The flag starts at 24 hours.")

            history = data[(data.line_id == pick) & (data.day <= day)]
            st.write("**Blood pressure drug dose at each 08:00 round since the line went in** (norepinephrine equivalent)")
            if history.dose_now.max() > 0:
                fig, ax = plt.subplots(figsize=(6, 2.6), facecolor="#F7F3EA")
                ax.set_facecolor("#F7F3EA")
                ax.plot(history.line_day, history.dose_now, marker="o", color="#2F5D50", lw=2)
                ax.spines[["top", "right"]].set_visible(False)
                ax.set_xlabel("Line day")
                ax.set_ylabel("Dose (mcg/kg/min)")
                ax.set_ylim(bottom=0)
                ax.grid(alpha=0.3)
                st.pyplot(fig)
            else:
                st.caption("No blood pressure drugs at any morning round since this line went in.")

            st.write("**Support ends by tomorrow? (experimental):** " + row.forecast)
            st.caption("On the demo data this model did no better than ranking patients by dose.")
            st.write("**Infection exposure factors:** " + (row.exposure or "none"))
            st.caption("A count of known risk factors, not a risk score.")

        with right:
            earlier = reviews[(reviews.line_id == pick) & (reviews.day < day)]
            last = earlier.iloc[-1] if len(earlier) else None

            if new_line:
                st.subheader("New line - why did it go in?")
            else:
                st.subheader("Today's review")

            # one tap: same reason as last time
            if last is not None and last.decision == "Keep":
                st.write(f"Last review (day {last.day}): **keep** - {last.reasons}")
                if st.button("Same as last time, still needed", type="primary"):
                    save_review({"day": day, "bed": row.bed, "line_id": pick, "reasons": last.reasons,
                                 "reason_status": "Active", "decision": "Keep", "note": "Reconfirmed",
                                 "senior_review": bool(last.senior_review), "reviewer": reviewer,
                                 "time": datetime.now().strftime("%Y-%m-%d %H:%M")},
                                "Reconfirmed with your name and the time.")
                st.write("Or record a new decision:")

            with st.form(f"review-{pick}-{day}"):  # fresh form for every line and day
                reasons = st.multiselect("Keeping this line because" if not new_line else "Line went in for", REASONS + WEAK)
                reason_status = st.radio("Is that reason still active?", ["Active", "Ceased", "Uncertain"], horizontal=True)
                decision = st.radio("Decision", ["Keep", "Remove", "Ask a senior"], horizontal=True)
                note = st.text_input("Note (optional)")
                saved = st.form_submit_button("Save review")
            if saved:
                if decision == "Keep" and not reasons:
                    st.error("Pick at least one reason for keeping it.")
                else:
                    weak = bool(reasons) and all(r in WEAK for r in reasons)
                    senior = decision == "Keep" and (weak or reason_status != "Active")
                    if senior and weak:
                        msg = ("warning", "Saved. Blood sampling or convenience alone is a weak reason, so a senior will check it.")
                    elif senior:
                        msg = ("warning", "Saved. You kept the line but the reason isn't active, so a senior will check it.")
                    else:
                        msg = ("success", "Saved with your name and the time.")
                    save_review({"day": day, "bed": row.bed, "line_id": pick, "reasons": "; ".join(reasons),
                                 "reason_status": reason_status, "decision": decision, "note": note,
                                 "senior_review": senior, "reviewer": reviewer,
                                 "time": datetime.now().strftime("%Y-%m-%d %H:%M")}, msg[1], msg[0])

            if "message" in st.session_state:
                kind, text = st.session_state.pop("message")
                (st.warning if kind == "warning" else st.success)(text)

            mine = reviews[reviews.line_id == pick]
            if len(mine):
                st.write("**Review log for this line**")
                st.dataframe(mine.iloc[::-1][["day", "decision", "reasons", "reason_status", "reviewer", "time"]],
                             hide_index=True)
