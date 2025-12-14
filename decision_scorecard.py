import json
import streamlit as st
from datetime import datetime
from openai import OpenAI

st.set_page_config(page_title="Decision Quiz", page_icon="🧭")

PILLARS = ["Security", "Energy", "Meaning / Fulfilment", "Connection", "Freedom / Optionality"]

WEIGHTS = {
    "Security": 1.2,
    "Energy": 1.3,
    "Meaning / Fulfilment": 1.0,
    "Connection": 1.2,
    "Freedom / Optionality": 1.1,
}

QUESTIONS = [
    ("decision", "What decision are you making? (one sentence)", "e.g. Take on this client / say no / change routine", 140),
    ("has_goal", "Do you have a goal that will be impacted by this decision?", "", None),
    ("goal", "State the goal (one sentence)", "e.g. Generate $200k service fees / be more present / improve fitness", 140),
    ("why_now", "Why does this decision exist now?", "One blunt line.", 220),
    ("upside", "Main upside (what do you gain if it works)?", "One blunt line.", 220),
    ("downside", "Main downside (what do you risk/lose)?", "One blunt line.", 220),
    ("cost_action", "Cost of doing it (time/money/energy)?", "One blunt line.", 220),
    ("cost_inaction", "Cost of NOT doing it (in 6–12 months)?", "One blunt line.", 220),
    ("returns", "Potential returns (what changes if it works)?", "One blunt line.", 220),
]

def weighted_score(scores):
    num = sum(scores[p] * WEIGHTS[p] for p in scores)
    den = sum(WEIGHTS.values())
    return round(num / den, 2)

def verdict(scores):
    avg = weighted_score(scores)
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

def ai_analyse(data):
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
        "decision": data.get("decision", ""),
        "goal": data.get("goal") if data.get("has_goal") == "Yes" else None,
        "why_now": data.get("why_now", ""),
        "perceived_upside": data.get("upside", ""),
        "perceived_downside": data.get("downside", ""),
        "cost_of_doing_it": data.get("cost_action", ""),
        "cost_of_not_doing_it": data.get("cost_inaction", ""),
        "potential_returns": data.get("returns", ""),
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

    out = json.loads(resp.choices[0].message.content.strip())

    scores = {}
    rats = {}
    for p in PILLARS:
        s = int(out["pillar_scores"].get(p, 5))
        scores[p] = max(1, min(10, s))
        rats[p] = str(out["pillar_rationales"].get(p, "No rationale provided.")).strip()[:220]

    act_now = str(out.get("act_now_outcome", "")).strip()[:320] or "Outcome unclear (insufficient input)."
    dont_act = str(out.get("dont_act_outcome", "")).strip()[:320] or "Outcome unclear (insufficient input)."
    goal_summary = str(out.get("goal_impact_summary", "")).strip()[:260] or "No goal impact summary provided."

    return scores, rats, act_now, dont_act, goal_summary

# -----------------------
# STATE INIT
# -----------------------
if "step" not in st.session_state:
    st.session_state.step = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "result" not in st.session_state:
    st.session_state.result = None

def reset():
    st.session_state.step = 0
    st.session_state.answers = {}
    st.session_state.result = None

st.title("Decision Quiz 🧭")
st.caption("One question at a time. Fast inputs. One verdict.")

colA, colB = st.columns([1, 1])
with colA:
    if st.button("↩ Reset"):
        reset()
with colB:
    st.caption(f"Step {st.session_state.step + 1} of {len(QUESTIONS)}")

# Skip the 'goal' question if has_goal = No
def should_skip(key):
    if key == "goal":
        return st.session_state.answers.get("has_goal") == "No"
    return False

# Find current question (advance past skippable)
while st.session_state.step < len(QUESTIONS) and should_skip(QUESTIONS[st.session_state.step][0]):
    st.session_state.step += 1

# -----------------------
# QUIZ FLOW
# -----------------------
if st.session_state.step < len(QUESTIONS):
    key, prompt, placeholder, max_chars = QUESTIONS[st.session_state.step]

    st.subheader(prompt)

    if key == "has_goal":
        val = st.radio("", ["No", "Yes"], horizontal=True, key="has_goal_radio")
        st.session_state.answers["has_goal"] = val
    else:
        default = st.session_state.answers.get(key, "")
        val = st.text_input("" if max_chars and max_chars <= 140 else "", value=default, placeholder=placeholder, key=f"in_{key}")
        # If longer prompts, use text_area
        if max_chars and max_chars > 140:
            val = st.text_area("", value=default, placeholder=placeholder, max_chars=max_chars, key=f"ta_{key}")
        st.session_state.answers[key] = (val or "").strip()

    c1, c2, c3 = st.columns([1, 1, 2])

    with c1:
        if st.session_state.step > 0 and st.button("⬅ Back"):
            st.session_state.step -= 1
            st.rerun()

    with c2:
        if st.button("Next ➜"):
            # Basic validation: don't allow blank decision
            if key == "decision" and not st.session_state.answers.get("decision"):
                st.error("Decision is required.")
            else:
                st.session_state.step += 1
                st.rerun()

    with c3:
        st.caption("Keep it blunt. One line is enough.")

else:
    st.subheader("Ready to analyse")

    with st.expander("Review your inputs"):
        for k, v in st.session_state.answers.items():
            st.write(f"**{k}**: {v}")

    if st.button("Analyse with AI ✅"):
        try:
            scores, rats, act_now, dont_act, goal_summary = ai_analyse(st.session_state.answers)
            st.session_state.result = {
                "scores": scores,
                "rats": rats,
                "act_now": act_now,
                "dont_act": dont_act,
                "goal_summary": goal_summary,
            }
            st.rerun()
        except Exception as e:
            st.error(f"AI analysis failed: {e}")

# -----------------------
# RESULTS
# -----------------------
if st.session_state.result:
    scores = st.session_state.result["scores"]
    rats = st.session_state.result["rats"]

    st.divider()
    st.subheader("Scores + rationale")
    for p in PILLARS:
        st.write(f"**{p}: {scores[p]}/10** — {rats[p]}")

    if st.session_state.answers.get("has_goal") == "Yes":
        st.subheader("Goal impact")
        st.write(st.session_state.result["goal_summary"])

    st.subheader("What changes")
    st.write(f"**If you action this now:** {st.session_state.result['act_now']}")
    st.write(f"**If you don’t action it now:** {st.session_state.result['dont_act']}")

    result, avg = verdict(scores)
    st.divider()
    st.markdown(f"## {result}")
    st.caption(f"Weighted score: {avg}/10")

    st.subheader("Lock-in")
    inaction = st.text_area("If I do nothing, what gets worse in 6–12 months?", max_chars=240)
    action = st.text_input("Next physical action (within 48 hours)", max_chars=120)

    if st.button("Lock decision 🔒"):
        if not inaction.strip() or not action.strip():
            st.error("Both fields required to lock the decision.")
        else:
            st.success("Decision locked. Stop thinking. Start acting.")
            st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
