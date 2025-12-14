import json
import streamlit as st
from datetime import datetime
from openai import OpenAI

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

WEIGHTS = {
    "Security": 1.2,
    "Energy": 1.3,
    "Meaning / Fulfilment": 1.0,
    "Connection": 1.2,
    "Freedom / Optionality": 1.1,
}

# -----------------------
# VERDICT LOGIC
# -----------------------
def weighted_score(scores):
    num = sum(scores[p] * WEIGHTS[p] for p in scores)
    den = sum(WEIGHTS.values())
    return round(num / den, 2)

def verdict(scores):
    avg = weighted_score(scores)

    # Hard guardrails
    if scores["Energy"] <= 3 and scores["Security"] <= 5:
        return "❌ NO — COST TOO HIGH", avg
    if scores["Connection"] <= 3 and scores["Meaning / Fulfilment"] <= 5:
        return "❌ NO — COST TOO HIGH", avg

    if avg >= 7.2:
        return "✅ YES — ACT", avg
    if avg >= 6.0 or scores["Energy"] <= 5 or scores["Connection"] <= 5:
        return "⚠️ REDESIGN — SAME GOAL, DIFFERENT SHAPE", avg
    if avg >= 5.0:
        return "⏸ WAIT — NOT RIPE", avg
    return "❌ NO — COST TOO HIGH", avg

# -----------------------
# AI ANALYSIS
# -----------------------
def ai_analyse(decision, goal, why_now, upside, downside, cost_action, cost_inaction, returns):
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

    system = (
        "You are a strict decision analyst. No therapy, no motivation, no fluff. "
        "Use ONLY the user's inputs. "
        "Return ONLY valid JSON with keys: "
        "pillar_scores, pillar_rationales, act_now_outcome, dont_act_outcome, goal_impact_summary. "
        "pillar_scores must be integers 1..10 for EACH pillar. "
        "pillar_rationales must be 1–2 short sentences per pillar explaining why that score was given. "
        "act_now_outcome and dont_act_outcome must be max 2 sentences each. "
        "If a goal is provided, prioritise scoring based on alignment to that goal."
    )

    payload = {
        "decision": decision,
        "goal": goal if goal else None,
        "why_now": why_now,
        "perceived_upside": upside,
        "perceived_downside": downside,
        "cost_of_doing_it": cost_action,
        "cost_of_not_doing_it": cost_inaction,
        "potential_returns": returns,
        "pillars": PILLARS,
        "score_scale": "1..10",
    }

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )

    data = json.loads(resp.choices[0].message.content.strip())

    scores = {}
    rationales = {}

    for p in PILLARS:
        s = int(data["pillar_scores"].get(p, 5))
        scores[p] = max(1, min(10, s))
        rationales[p] = data["pillar_rationales"].get(p, "No rationale provided.")[:220]

    return (
        scores,
        rationales,
        data.get("act_now_outcome", "")[:300],
        data.get("dont_act_outcome", "")[:300],
        data.get("goal_impact_summary", "")[:240],
    )

# -----------------------
# UI
# -----------------------
st.title("Decision Engine 🧭")
st.caption("One-shot analysis. One verdict. Then action.")

decision = st.text_input("Decision (one sentence)")

st.divider()
st.subheader("Goal alignment")

has_goal = st.radio(
    "Do you have a goal that will be impacted by this decision?",
    ["No", "Yes"],
    horizontal=True
)

goal = ""
if has_goal == "Yes":
    goal = st.text_input("State the goal (one sentence)")

with st.expander("AI intake (keep it short)"):
    why_now = st.text_area("Why does this decision exist now?", max_chars=240)
    upside = st.text_area("Main upside", max_chars=240)
    downside = st.text_area("Main downside", max_chars=240)
    cost_action = st.text_area("Cost of doing it", max_chars=240)
    cost_inaction = st.text_area("Cost of not doing it", max_chars=240)
    returns = st.text_area("Potential returns", max_chars=240)

if st.button("Analyse with AI"):
    scores, rats, act_now, dont_act, goal_summary = ai_analyse(
        decision, goal, why_now, upside, downside, cost_action, cost_inaction, returns
    )
    st.session_state.update({
        "scores": scores,
        "rats": rats,
        "act_now": act_now,
        "dont_act": dont_act,
        "goal_summary": goal_summary,
    })

scores = st.session_state.get("scores", {})

if scores:
    st.subheader("Why these scores")
    for p in PILLARS:
        st.write(f"**{p}: {scores[p]}/10** — {st.session_state['rats'][p]}")

    if goal:
        st.subheader("Goal impact")
        st.write(st.session_state["goal_summary"])

    st.subheader("What changes")
    st.write(f"**If you action this now:** {st.session_state['act_now']}")
    st.write(f"**If you don’t action it now:** {st.session_state['dont_act']}")

    result, avg = verdict(scores)
    st.divider()
    st.markdown(f"## {result}")
    st.caption(f"Weighted score: {avg}/10")

    st.subheader("Lock-in")
    inaction = st.text_area("If I do nothing, what gets worse in 6–12 months?", max_chars=240)
    action = st.text_input("Next physical action (within 48 hours)", max_chars=120)

    if st.button("Lock decision"):
        if inaction and action:
            st.success("Decision locked. Stop thinking. Start acting.")
            st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
