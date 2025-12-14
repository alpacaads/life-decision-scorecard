import json
from datetime import datetime
from pathlib import Path
import streamlit as st

DATA_FILE = Path("decisions.json")

PILLARS = [
    "Family (wife & son)",
    "Business (stability & growth)",
    "Physical health",
    "Mental health / peace",
]

SCORES = [-2, -1, 0, 1, 2]

def load_decisions():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def save_decisions(decisions):
    DATA_FILE.write_text(json.dumps(decisions, indent=2), encoding="utf-8")

def compute_verdict(scores_dict, inaction_cost, fragility):
    any_minus_2 = any(v == -2 for v in scores_dict.values())
    total = sum(scores_dict.values())

    high_inaction = len(inaction_cost.strip()) >= 20
    reduces_fragility = fragility == "Reduces fragility (more buffer)"

    if any_minus_2:
        return "NO (or redesign)", total
    if total > 0:
        return "YES", total
    if total == 0 and (high_inaction or reduces_fragility):
        return "YES", total
    if reduces_fragility:
        return "YES", total
    return "REDESIGN / WAIT", total

st.set_page_config(page_title="Life Decision Scorecard", page_icon="✅")

st.title("Life Decision Scorecard")
st.caption("Impact-based decisions across your core life pillars.")

decisions = load_decisions()

with st.form("scorecard"):
    decision = st.text_input("Decision (one sentence)")
    date = st.date_input("Date", value=datetime.now().date())

    st.subheader("Pillar impact (–2 to +2)")
    scores = {}
    for pillar in PILLARS:
        scores[pillar] = st.select_slider(pillar, options=SCORES, value=0)

    st.subheader("Inaction cost (6–12 months)")
    inaction_cost = st.text_area("If I do nothing, what’s the cost?")

    st.subheader("Fragility test")
    fragility = st.radio(
        "Does this increase or reduce fragility?",
        ["Reduces fragility (more buffer)", "Neutral", "Increases fragility"],
    )

    next_action = st.text_input("Next smallest action (24–48 hrs)")
    submitted = st.form_submit_button("Compute + Save")

if submitted and decision.strip():
    verdict, total = compute_verdict(scores, inaction_cost, fragility)

    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "date": str(date),
        "decision": decision,
        "scores": scores,
        "total_score": total,
        "inaction_cost": inaction_cost,
        "fragility": fragility,
        "next_action": next_action,
        "verdict": verdict,
    }

    decisions.insert(0, entry)
    save_decisions(decisions)

    st.success(f"Verdict: {verdict} | Total score: {total}")
