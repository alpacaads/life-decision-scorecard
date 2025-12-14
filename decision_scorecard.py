import json
import streamlit as st
from datetime import datetime
from openai import OpenAI

st.set_page_config(page_title="Decision Engine", page_icon="🧭")

# -----------------------
# CONFIG
# -----------------------
PILLARS = ["Security", "Energy", "Meaning / Fulfilment", "Connection", "Freedom / Optionality"]
SCORES = [-2, -1, 0, 1, 2]

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

def clamp_score(x):
    try:
        x = int(x)
    except Exception:
        return 0
    return max(-2, min(2, x))

def ai_analyse(decision, why_now, upside, downside, cost_action, cost_inaction, returns):
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing OPENAI_API_KEY in Streamlit Secrets.")
    client = OpenAI(api_key=api_key)

    system = (
        "You are a strict decision analyst. "
        "Your job: map the user's inputs to 5 pillar scores (-2..2) and a short reason. "
        "No therapy. No motivational tone. No extra suggestions."
        "Return ONLY valid JSON with keys: pillar_scores, reason."
    )

    user = {
        "decision": decision,
        "why_now": why_now,
        "perceived_upside": upside,
        "perceived_downside": downside,
        "cost_of_doing_it": cost_action,
        "cost_of_not_doing_it": cost_inaction,
        "potential_returns": returns,
        "pillars": PILLARS,
        "score_scale": "-2..2 (integer)",
        "rules": [
            "Scores must be integers -2..2",
            "Give a single 'reason' string, max ~2 sentences, impact-focused",
            "If information is missing, infer cautiously and score nearer to 0",
        ],
    }

    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user)},
        ],
    )

    text = resp.choices[0].message.content.strip()
    data = json.loads(text)  # if this fails, we want it to fail loudly rather than guess
    raw = data.get("pillar_scores", {})

    scores = {}
    for p in PILLARS:
        scores[p] = clamp_score(raw.get(p, 0))

    reason = str(data.get("reason", "")).strip()[:280]
    if not reason:
        reason = "Reason unavailable (AI returned empty)."
    return scores, reason

# -----------------------
# UI
# -----------------------
st.title("Decision Engine 🧭")
st.caption("One-shot analysis. One verdict. Then action.")

decision = st.text_input("Decision (one sentence)", placeholder="e.g. Take on this client / Say no / Change routine")

with st.expander("AI Intake (keep it short)"):
    why_now = st.text_area("Why does this decision exist now?", max_chars=240)
    upside = st.text_area("Main upside (what you believe you gain)", max_chars=240)
    downside = st.text_area("Main downside (what you believe you risk/lose)", max_chars=240)
    cost_action = st.text_area("Cost of doing it (time/money/energy)", max_chars=240)
    cost_inaction = st.text_area("Cost of not doing it (6–12 months)", max_chars=240)
    returns = st.text_area("Potential returns (what changes if it works)", max_chars=240)

st.divider()

col1, col2 = st.columns(2)
with col1:
    use_ai = st.toggle("Use AI to score pillars", value=True)
with col2:
    st.caption("Tip: AI mode is best for messy decisions. Manual mode is fastest.")

scores = {p: 0 for p in PILLARS}
ai_reason = ""

if use_ai:
    if st.button("Analyse with AI"):
        if not decision.strip():
            st.error("Write the decision first.")
        else:
            try:
                scores, ai_reason = ai_analyse(decision, why_now, upside, downside, cost_action, cost_inaction, returns)
                st.session_state["scores"] = scores
                st.session_state["ai_reason"] = ai_reason
            except Exception as e:
                st.error(f"AI analysis failed: {e}")

# Manual scoring fallback (always available)
st.subheader("Pillar scores (–2 to +2)")
scores = st.session_state.get("scores", scores)
for p in PILLARS:
    scores[p] = st.select_slider(p, options=SCORES, value=int(scores.get(p, 0)))

st.session_state["scores"] = scores

result = ""
if st.button("Get System Verdict"):
    if not decision.strip():
        st.error("Write the decision first.")
    else:
        result = verdict(scores)
        st.session_state["verdict"] = result

if st.session_state.get("ai_reason"):
    st.info(st.session_state["ai_reason"])

if st.session_state.get("verdict"):
    st.divider()
    st.subheader("SYSTEM VERDICT")
    st.markdown(f"## {st.session_state['verdict']}")
    st.caption("No overrides. Lock it and act.")

    st.subheader("Lock-in (required)")
    inaction = st.text_area("If I do nothing, what gets worse in 6–12 months?", max_chars=240)
    action = st.text_input("Next physical action (within 48 hours)", max_chars=120)

    if st.button("Lock Decision"):
        if not inaction.strip() or not action.strip():
            st.error("Both fields required to lock the decision.")
        else:
            st.success("Decision locked. Stop thinking. Start acting.")
            st.caption(f"Logged on {datetime.now().strftime('%Y-%m-%d %H:%M')}")
