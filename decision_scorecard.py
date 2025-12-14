import streamlit as st
from datetime import datetime

st.set_page_config(page_title="Decision Engine", page_icon="🧭")

# -----------------------
# CONFIG
# -----------------------
PILLARS = [
    "Security",
    "Energy",
    "Meaning / Fulfilment",
    "Connection",
    "Freedom / Optionality",
]

SCORES = [-2, -1, 0, 1, 2]

# -----------------------
# VERDICT LOGIC
# -----------------------
def verdict(scores):
    total = sum(scores.values())
    any_minus_2 = any(v == -2 for v in scores.values())

    security = scores["Security"]
    energy = scores["Energy"]
    freedom = scores["Freedom / Optionality"]
    connection = scores["Connection"]

    if any_minus_2:
        return "❌ NO — COST TOO HIGH"

    if energy <= -1 and security <= 0:
        return "❌ NO — COST TOO HIGH"

    if total >= 3 or (security >= 1 and freedom >= 1):
        return "✅ YES — ACT"

    if energy <= -1 or connection <= -1:
        return "⚠️ REDESIGN — SAME GOAL, DIFFERENT SHAPE"

    return "⏸ WAIT — NOT RIPE"

# -----------------------
# UI
# -----------------------
st.title("Decision Engine 🧭")
st.caption("The system decides. You provide honest inputs.")

decision = st.text_input(
    "Decision (one sentence only)",
    placeholder="e.g. Take on this client / Change my routine / Say no"
)

st.divider()
st.subheader("Score the impact over 6–12 months")

scores = {}
for pillar in PILLARS:
    scores[pillar] = st.select_slider(
        pillar,
        options=SCORES,
        value=0,
        help="First instinct only. Do not justify."
    )

ready = st.button("Get Decision")

# -----------------------
# RESULT
# -----------------------
if ready:
    if not decision.strip():
        st.error("Write the decision first.")
    else:
        result = verdict(scores)

        st.divider()
        st.subheader("SYSTEM VERDICT")
        st.markdown(f"## {result}")

        st.caption("This verdict cannot be overridden.")

        st.divider()
        st.subheader("Lock-in (required)")

        inaction = st.text_area(
            "If I do nothing, what gets worse in 6–12 months?",
            max_chars=240,
            placeholder="Be blunt. No stories."
        )

        action = st.text_input(
            "Next physical action (within 48 hours)",
            max_chars=120,
            placeholder="One concrete step only"
        )

        if st.button("Lock Decision"):
            if not inaction.strip() or not action.strip():
                st.error("Both fields required to lock the decision.")
            else:
                st.success("Decision locked. Stop thinking. Start acting.")
                st.caption(f"Logged on {datetime.now().strftime('%Y-%m-%d %H:%M')}")
