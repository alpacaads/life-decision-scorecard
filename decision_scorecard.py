import json
import time
import streamlit as st
from datetime import datetime
from openai import OpenAI

st.set_page_config(page_title="Decision Protocol", page_icon="🧭")

# -----------------------
# Helpers
# -----------------------
def client():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def safe_json_loads(text: str):
    return json.loads((text or "").strip())

def clamp_int(x, lo, hi, default):
    try:
        x = int(x)
    except Exception:
        return default
    return max(lo, min(hi, x))

def normalise_weights(w: dict, keys: list):
    cleaned = {}
    for k in keys:
        try:
            v = float(w.get(k, 0))
        except Exception:
            v = 0.0
        cleaned[k] = max(0.0, v)
    s = sum(cleaned.values())
    if s <= 0:
        return {k: 1.0 / len(keys) for k in keys}
    return {k: cleaned[k] / s for k in keys}

def weighted_score(scores: dict, weights: dict):
    return round(sum(float(scores[k]) * float(weights.get(k, 0)) for k in scores), 2)

def verdict_from_avg(avg: float):
    if avg >= 7.6:
        return "✅ YES — ACT"
    if avg >= 6.4:
        return "⚠️ REDESIGN — SAME GOAL, DIFFERENT SHAPE"
    if avg >= 5.5:
        return "⏸ WAIT — NOT RIPE"
    return "❌ NO — COST TOO HIGH"

def values_weight_table(values_ranked, weights, scores=None):
    # Simple matrix view in a dataframe-like table
    rows = []
    for v in values_ranked:
        w = float(weights.get(v, 0))
        row = {
            "What matters": v,
            "Weight": f"{round(w*100)}%"
        }
        if scores is not None:
            s = int(scores.get(v, 5))
            row["Score"] = f"{s}/10"
            row["Weighted"] = round(s * w, 2)
        rows.append(row)
    st.table(rows)

# -----------------------
# Loading animation between steps
# -----------------------
def go_to(step: int):
    st.session_state._target_step = step
    st.session_state._transition = True
    st.rerun()

def handle_transition():
    if st.session_state.get("_transition"):
        with st.spinner("Loading…"):
            time.sleep(0.35)
        st.session_state.step = st.session_state.get("_target_step", st.session_state.step)
        st.session_state._transition = False
        st.rerun()

# -----------------------
# AI Calls
# -----------------------
def ai_build_understanding(payload: dict):
    """
    Must return JSON with:
      one_liner: str
      understanding: str
      weights: {value: float, ...}
      assumptions: [str,...]
    """
    system = (
        "You are a strict decision analyst. No therapy. No motivational tone. No fluff. "
        "Never say the word 'user'. Speak directly to 'You'. "
        "Return ONLY valid JSON with keys: one_liner, understanding, weights, assumptions. "
        "one_liner must be ONE blunt sentence describing what You want to achieve in this situation. "
        "understanding must be a short paragraph (max 4 lines) in plain language. No bullet points. "
        "weights must assign a non-negative number to EACH item in values_ranked. "
        "Higher-ranked items should generally get higher weight, adjusted by the stated impacts. "
        "assumptions max 4 short lines."
    )

    resp = client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return safe_json_loads(resp.choices[0].message.content)

def ai_score_and_direct(payload: dict):
    """
    Returns:
      scores: {value:int 1..10}
      score_rationales: {value:str}
      act_now_future: str
      dont_act_future: str
      do_now: [str,str,str]
    """
    system = (
        "You are a strict decision analyst. No therapy. No fluff. No hedging. "
        "Never say the word 'user'. Speak directly to 'You'. "
        "Use ONLY the provided inputs and the approved understanding. "
        "Return ONLY valid JSON with keys: scores, score_rationales, act_now_future, dont_act_future, do_now. "
        "scores must be integers 1..10 for EACH value. "
        "score_rationales must be 1–2 short sentences per value. "
        "act_now_future and dont_act_future must be max 2 sentences each, concrete. "
        "do_now must be exactly 3 action strings You can do in the next 48 hours."
    )

    resp = client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return safe_json_loads(resp.choices[0].message.content)

# -----------------------
# State
# -----------------------
if "step" not in st.session_state:
    st.session_state.step = 0
if "a" not in st.session_state:
    st.session_state.a = {}
if "understanding" not in st.session_state:
    st.session_state.understanding = None
if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "_transition" not in st.session_state:
    st.session_state._transition = False
if "_target_step" not in st.session_state:
    st.session_state._target_step = 0

def reset():
    st.session_state.step = 0
    st.session_state.a = {}
    st.session_state.understanding = None
    st.session_state.analysis = None
    st.session_state._transition = False
    st.session_state._target_step = 0

# -----------------------
# UI
# -----------------------
st.title("Decision Protocol 🧭")
st.caption("One step at a time. AI adapts to what You say matters.")

handle_transition()

topL, topR = st.columns([1, 1])
with topL:
    if st.button("↩ Reset"):
        reset()
with topR:
    st.caption(f"Step {st.session_state.step + 1} / 6")

# -----------------------
# STEP 0 — Decision
# -----------------------
if st.session_state.step == 0:
    st.subheader("What decision are You making?")
    decision = st.text_input(
        "",
        value=st.session_state.a.get("decision", ""),
        placeholder="One sentence. e.g. Take on this client / say no / hire a VA",
        max_chars=140,
    )
    st.session_state.a["decision"] = (decision or "").strip()

    st.caption("Keep it blunt. One sentence.")

    c1, c2 = st.columns([1, 1])
    with c2:
        if st.button("Next ➜"):
            if not st.session_state.a["decision"]:
                st.error("Decision is required.")
            else:
                go_to(1)

# -----------------------
# STEP 1 — What matters (ranked)
# -----------------------
elif st.session_state.step == 1:
    st.subheader("What matters most in Your life? (ranked)")
    st.write("Type one item per line in order. **Top = #1 most important.**")

    values_text = st.text_area(
        "",
        value=st.session_state.a.get("values_text", "Family\nBusiness stability\nPhysical health\nMental peace"),
        placeholder="e.g.\nFamily\nBusiness stability\nHealth\nPeace of mind",
        height=160,
    )
    st.session_state.a["values_text"] = values_text
    values_ranked = [v.strip() for v in values_text.splitlines() if v.strip()]

    if len(values_ranked) < 2:
        st.warning("Add at least 2 items so trade-offs are real.")

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go_to(0)
    with c2:
        if st.button("Next ➜"):
            if len(values_ranked) < 2:
                st.error("Please enter at least 2 ranked items.")
            else:
                st.session_state.a["values_ranked"] = values_ranked
                go_to(2)

# -----------------------
# STEP 2 — Optional goal
# -----------------------
elif st.session_state.step == 2:
    st.subheader("Goal (optional)")

    has_goal = st.radio(
        "Is there a specific goal impacted by this decision?",
        ["No", "Yes"],
        horizontal=True,
        index=1 if st.session_state.a.get("has_goal") == "Yes" else 0,
    )
    st.session_state.a["has_goal"] = has_goal

    if has_goal == "Yes":
        goal = st.text_input(
            "State the goal (one sentence)",
            value=st.session_state.a.get("goal", ""),
            placeholder="e.g. Make $200k in service fees this year",
            max_chars=140,
        )
        st.session_state.a["goal"] = (goal or "").strip()
    else:
        st.session_state.a["goal"] = ""

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go_to(1)
    with c2:
        if st.button("Next ➜"):
            if has_goal == "Yes" and not st.session_state.a["goal"]:
                st.error("If You selected Yes, state the goal.")
            else:
                go_to(3)

# -----------------------
# STEP 3 — Impact per value
# -----------------------
elif st.session_state.step == 3:
    st.subheader("Impact check (one by one)")
    values_ranked = st.session_state.a.get("values_ranked", [])
    if not values_ranked:
        go_to(1)

    if "impact_i" not in st.session_state.a:
        st.session_state.a["impact_i"] = 0

    i = st.session_state.a["impact_i"]
    v = values_ranked[i]

    st.caption(f"{i+1} of {len(values_ranked)}")
    st.write(f"### How will this decision impact **{v}**?")

    impacts = st.session_state.a.get("impacts", {})
    current = impacts.get(v, "")

    ans = st.text_area(
        "",
        value=current,
        placeholder="One blunt line. Mention + or - impact.",
        max_chars=240,
        height=110,
    )
    impacts[v] = (ans or "").strip()
    st.session_state.a["impacts"] = impacts

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("⬅ Back"):
            if i == 0:
                go_to(2)
            else:
                st.session_state.a["impact_i"] = i - 1
                go_to(3)
    with c2:
        if st.button("Next ➜"):
            if not impacts[v]:
                st.error("Write one line. Don’t overthink it.")
            else:
                if i < len(values_ranked) - 1:
                    st.session_state.a["impact_i"] = i + 1
                    go_to(3)
                else:
                    go_to(4)
    with c3:
        st.caption("Short. Concrete. No essays.")

# -----------------------
# STEP 4 — AI understanding (Confirm / Adjust) + weight matrix
# -----------------------
elif st.session_state.step == 4:
    st.subheader("AI understanding (confirm before scoring)")

    a = st.session_state.a
    values_ranked = a.get("values_ranked", [])
    impacts = a.get("impacts", {})
    correction = a.get("correction", "").strip()

    payload = {
        "decision": a.get("decision", ""),
        "values_ranked": values_ranked,
        "goal": a.get("goal", "") if a.get("has_goal") == "Yes" else None,
        "impacts_by_value": impacts,
        "correction": correction if correction else None,
    }

    if st.session_state.understanding is None:
        with st.spinner("Building understanding…"):
            u = ai_build_understanding(payload)
            u["weights"] = normalise_weights(u.get("weights", {}), values_ranked)
            st.session_state.understanding = u

    u = st.session_state.understanding
    one_liner = (u.get("one_liner", "") or "").strip()
    understanding = (u.get("understanding", "") or "").strip()

    # Top: blunt one-liner
    st.markdown(f"## {one_liner if one_liner else 'You want to make a clean call and move forward.'}")

    # Middle: short paragraph, not bullets
    if understanding:
        st.write(understanding)

    # Bottom: matrix of weights
    st.divider()
    st.subheader("What will matter most in the scoring")
    values_weight_table(values_ranked, u["weights"])

    # Confirm / Adjust buttons
    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])

    with c1:
        if st.button("⬅ Back"):
            go_to(3)

    with c2:
        if st.button("Confirm ✅"):
            # lock understanding and proceed
            go_to(5)

    with c3:
        if st.button("Adjust ✍️"):
            st.session_state.a["_show_adjust"] = True
            st.rerun()

    if st.session_state.a.get("_show_adjust"):
        corr = st.text_area(
            "What’s wrong or missing? (one blunt correction)",
            value=st.session_state.a.get("correction", ""),
            max_chars=240,
            height=90,
        )
        st.session_state.a["correction"] = (corr or "").strip()

        cc1, cc2 = st.columns([1, 1])
        with cc2:
            if st.button("Redo understanding ➜"):
                if not st.session_state.a["correction"]:
                    st.error("Write the correction first.")
                else:
                    st.session_state.understanding = None
                    st.session_state.a["_show_adjust"] = False
                    go_to(4)

# -----------------------
# STEP 5 — Scoring + Verdict + Matrix + Do now
# -----------------------
elif st.session_state.step == 5:
    st.subheader("Scoring + verdict")

    a = st.session_state.a
    values_ranked = a.get("values_ranked", [])
    impacts = a.get("impacts", {})
    u = st.session_state.understanding or {}
    weights = normalise_weights(u.get("weights", {}), values_ranked)

    if st.session_state.analysis is None:
        payload = {
            "decision": a.get("decision", ""),
            "goal": a.get("goal", "") if a.get("has_goal") == "Yes" else None,
            "values_ranked": values_ranked,
            "impacts_by_value": impacts,
            "approved_one_liner": u.get("one_liner", ""),
            "approved_understanding": u.get("understanding", ""),
            "approved_weights": weights,
        }

        with st.spinner("Scoring…"):
            out = ai_score_and_direct(payload)

        scores = {}
        rats = {}
        for v in values_ranked:
            scores[v] = clamp_int(out.get("scores", {}).get(v, 5), 1, 10, 5)
            rats[v] = (str(out.get("score_rationales", {}).get(v, "")).strip()[:220] or "No rationale provided.")

        do_now = out.get("do_now", [])
        if not isinstance(do_now, list):
            do_now = []
        do_now = [str(x).strip() for x in do_now if str(x).strip()][:3]
        while len(do_now) < 3:
            do_now.append("Write the next concrete step in 1 line and do it today.")

        act_now = (str(out.get("act_now_future", "")).strip()[:320] or "Outcome unclear (insufficient input).")
        dont_act = (str(out.get("dont_act_future", "")).strip()[:320] or "Outcome unclear (insufficient input).")

        avg = weighted_score(scores, weights)
        vtxt = verdict_from_avg(avg)

        st.session_state.analysis = {
            "scores": scores,
            "rats": rats,
            "weights": weights,
            "avg": avg,
            "verdict": vtxt,
            "act_now": act_now,
            "dont_act": dont_act,
            "do_now": do_now,
        }

    out = st.session_state.analysis
    scores = out["scores"]

    # Matrix: values + weights + scores
    st.subheader("Matrix (what matters × weight × score)")
    values_weight_table(values_ranked, out["weights"], scores=scores)

    st.divider()
    st.subheader("Rationales")
    for v in values_ranked:
        st.write(f"**{v}: {scores[v]}/10** — {out['rats'][v]}")

    st.subheader("What changes")
    st.write(f"**If You action this now:** {out['act_now']}")
    st.write(f"**If You don’t action it now:** {out['dont_act']}")

    st.divider()
    st.markdown(f"## {out['verdict']}")
    st.caption(f"Weighted score: {out['avg']}/10")

    st.subheader("Do this right now (no debate)")
    for i, step in enumerate(out["do_now"], start=1):
        st.write(f"{i}. {step}")

    st.divider()
    st.subheader("Lock-in")
    lock_action = st.text_input("First action You will complete in the next 48 hours", max_chars=120)
    when = st.text_input("When will You do it? (date/time)", placeholder="e.g. Today 3pm", max_chars=60)

    if st.button("Lock decision 🔒"):
        if not lock_action.strip() or not when.strip():
            st.error("Both fields required.")
        else:
            st.success("Locked. Stop thinking. Start acting.")
            st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
            st.write(f"**Committed action:** {lock_action}")
            st.write(f"**When:** {when}")
