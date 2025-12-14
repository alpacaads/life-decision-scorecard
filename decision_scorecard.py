import json
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
    text = (text or "").strip()
    return json.loads(text)

def clamp_int(x, lo, hi, default):
    try:
        x = int(x)
    except Exception:
        return default
    return max(lo, min(hi, x))

def normalise_weights(w: dict, keys: list):
    # Ensure all keys exist, non-negative, sum to 1
    cleaned = {}
    for k in keys:
        v = w.get(k, 0)
        try:
            v = float(v)
        except Exception:
            v = 0.0
        cleaned[k] = max(0.0, v)

    s = sum(cleaned.values())
    if s <= 0:
        # equal weights
        return {k: 1.0 / len(keys) for k in keys}
    return {k: cleaned[k] / s for k in keys}

def weighted_score(scores: dict, weights: dict):
    # scores 1..10
    total = 0.0
    for k, s in scores.items():
        total += float(s) * float(weights.get(k, 0))
    return round(total, 2)

def verdict_from_avg(avg: float):
    # Simple, decisive thresholds (can tune later)
    if avg >= 7.6:
        return "✅ YES — ACT"
    if avg >= 6.4:
        return "⚠️ REDESIGN — SAME GOAL, DIFFERENT SHAPE"
    if avg >= 5.5:
        return "⏸ WAIT — NOT RIPE"
    return "❌ NO — COST TOO HIGH"

# -----------------------
# AI Calls
# -----------------------
def ai_build_understanding(payload: dict):
    """
    Returns:
      {
        "understanding_summary": str,
        "key_tradeoffs": [str,...],
        "weights": {value: float, ...},  # sums to 1
        "assumptions": [str,...]
      }
    """
    system = (
        "You are a strict decision analyst. No therapy. No motivational tone. No fluff. "
        "Use ONLY the user's inputs. "
        "Return ONLY valid JSON with keys: understanding_summary, key_tradeoffs, weights, assumptions. "
        "weights must assign a non-negative number to EACH value in values_ranked and reflect what matters most to the user "
        "(higher for higher-ranked values), adjusted by what the user wrote about impacts. "
        "understanding_summary must be max 5 lines. key_tradeoffs max 5 bullets. assumptions max 5 bullets."
    )

    resp = client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    data = safe_json_loads(resp.choices[0].message.content)
    return data

def ai_score_and_direct(payload: dict):
    """
    Returns:
      {
        "scores": {value: int 1..10, ...},
        "score_rationales": {value: str, ...},
        "act_now_future": str (<=2 sentences),
        "dont_act_future": str (<=2 sentences),
        "do_now": [str, str, str]  # exact actions
      }
    """
    system = (
        "You are a strict decision analyst. No therapy. No fluff. No hedging. "
        "Use ONLY the user's inputs and the approved understanding. "
        "Return ONLY valid JSON with keys: scores, score_rationales, act_now_future, dont_act_future, do_now. "
        "scores must be integers 1..10 for EACH value. "
        "score_rationales must be 1–2 short sentences per value explaining the score. "
        "act_now_future and dont_act_future must be max 2 sentences each, concrete. "
        "do_now must be exactly 3 bullet actions (strings) that the user can do in the next 48 hours."
    )

    resp = client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    data = safe_json_loads(resp.choices[0].message.content)
    return data

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

def reset():
    st.session_state.step = 0
    st.session_state.a = {}
    st.session_state.understanding = None
    st.session_state.analysis = None

# -----------------------
# UI
# -----------------------
st.title("Decision Protocol 🧭")
st.caption("One step at a time. AI adapts to what *you* say matters.")

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
    st.subheader("What decision are you making?")
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
                st.session_state.step = 1
                st.rerun()

# -----------------------
# STEP 1 — What matters (ranked)
# -----------------------
elif st.session_state.step == 1:
    st.subheader("What matters most in your life? (ranked)")
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
        st.warning("Add at least 2 items so the system can weight trade-offs properly.")

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            st.session_state.step = 0
            st.rerun()
    with c2:
        if st.button("Next ➜"):
            if len(values_ranked) < 2:
                st.error("Please enter at least 2 ranked items.")
            else:
                st.session_state.a["values_ranked"] = values_ranked
                st.session_state.step = 2
                st.rerun()

# -----------------------
# STEP 2 — Optional goal
# -----------------------
elif st.session_state.step == 2:
    st.subheader("Goal (optional)")

    has_goal = st.radio(
        "Is there a specific life goal impacted by this decision?",
        ["No", "Yes"],
        horizontal=True,
        index=1 if st.session_state.a.get("has_goal") == "Yes" else 0,
    )
    st.session_state.a["has_goal"] = has_goal

    goal = st.session_state.a.get("goal", "")
    if has_goal == "Yes":
        goal = st.text_input(
            "State the goal (one sentence)",
            value=goal,
            placeholder="e.g. Make $200k in service fees this year",
            max_chars=140,
        )
        st.session_state.a["goal"] = (goal or "").strip()
    else:
        st.session_state.a["goal"] = ""

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("Next ➜"):
            if has_goal == "Yes" and not st.session_state.a["goal"]:
                st.error("If you selected Yes, please state the goal.")
            else:
                st.session_state.step = 3
                st.rerun()

# -----------------------
# STEP 3 — Impact per value (one by one)
# -----------------------
elif st.session_state.step == 3:
    st.subheader("Impact check (one by one)")
    values_ranked = st.session_state.a.get("values_ranked", [])
    if not values_ranked:
        st.session_state.step = 1
        st.rerun()

    # which value index are we on?
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
            # If first value, go back to goal step
            if i == 0:
                st.session_state.step = 2
            else:
                st.session_state.a["impact_i"] = i - 1
            st.rerun()

    with c2:
        if st.button("Next ➜"):
            if not impacts[v]:
                st.error("Write one line. Don’t overthink it.")
            else:
                if i < len(values_ranked) - 1:
                    st.session_state.a["impact_i"] = i + 1
                    st.rerun()
                else:
                    # Done impacts
                    st.session_state.step = 4
                    st.rerun()

    with c3:
        st.caption("Short. Concrete. No essays.")

# -----------------------
# STEP 4 — AI summary + confirmation gate
# -----------------------
elif st.session_state.step == 4:
    st.subheader("AI understanding (confirm before scoring)")

    a = st.session_state.a
    values_ranked = a.get("values_ranked", [])
    impacts = a.get("impacts", {})

    correction = st.session_state.a.get("correction", "")

    payload = {
        "decision": a.get("decision", ""),
        "values_ranked": values_ranked,
        "goal": a.get("goal", "") if a.get("has_goal") == "Yes" else None,
        "impacts_by_value": impacts,
        "user_correction_if_any": correction or None,
    }

    # Build understanding if missing (or if user asked to redo)
    if st.session_state.understanding is None:
        with st.spinner("Building understanding..."):
            u = ai_build_understanding(payload)
            # Normalise weights
            u["weights"] = normalise_weights(u.get("weights", {}), values_ranked)
            st.session_state.understanding = u

    u = st.session_state.understanding

    st.write("### What I think is going on")
    st.write(u.get("understanding_summary", ""))

    tradeoffs = u.get("key_tradeoffs", [])
    if tradeoffs:
        st.write("### Key trade-offs")
        for t in tradeoffs[:5]:
            st.write(f"- {t}")

    st.write("### What the system is prioritising (weights)")
    # show weights in ranked order
    for v in values_ranked:
        st.write(f"- **{v}**: {round(u['weights'].get(v, 0)*100)}%")

    assumptions = u.get("assumptions", [])
    if assumptions:
        with st.expander("Assumptions (only if needed)"):
            for x in assumptions[:5]:
                st.write(f"- {x}")

    st.divider()
    ok = st.radio("Is this accurate?", ["Yes", "No"], horizontal=True, index=0)

    if ok == "No":
        corr = st.text_area(
            "What did I get wrong? (one blunt correction)",
            value=st.session_state.a.get("correction", ""),
            max_chars=240,
            height=90,
        )
        st.session_state.a["correction"] = (corr or "").strip()

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("⬅ Back"):
                st.session_state.step = 3
                st.rerun()
        with c2:
            if st.button("Redo understanding ➜"):
                if not st.session_state.a["correction"]:
                    st.error("Write a correction first.")
                else:
                    # force rebuild understanding
                    st.session_state.understanding = None
                    st.rerun()
    else:
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("⬅ Back"):
                st.session_state.step = 3
                st.rerun()
        with c2:
            if st.button("Proceed to scoring ➜"):
                st.session_state.step = 5
                st.rerun()

# -----------------------
# STEP 5 — Scoring + Verdict + Do now
# -----------------------
elif st.session_state.step == 5:
    st.subheader("Scoring + verdict")

    a = st.session_state.a
    values_ranked = a.get("values_ranked", [])
    impacts = a.get("impacts", {})
    u = st.session_state.understanding or {}

    if st.session_state.analysis is None:
        payload = {
            "decision": a.get("decision", ""),
            "goal": a.get("goal", "") if a.get("has_goal") == "Yes" else None,
            "values_ranked": values_ranked,
            "impacts_by_value": impacts,
            "approved_understanding_summary": u.get("understanding_summary", ""),
            "approved_weights": u.get("weights", {}),
        }
        with st.spinner("Scoring..."):
            out = ai_score_and_direct(payload)

            # clamp and normalise
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

            weights = normalise_weights(u.get("weights", {}), values_ranked)
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

    st.write("### Scores (what matters to you)")
    for v in values_ranked:
        st.write(f"**{v}: {out['scores'][v]}/10** — {out['rats'][v]}")

    st.write("### What changes")
    st.write(f"**If you action this now:** {out['act_now']}")
    st.write(f"**If you don’t action it now:** {out['dont_act']}")

    st.divider()
    st.markdown(f"## {out['verdict']}")
    st.caption(f"Weighted score: {out['avg']}/10")

    st.subheader("Do this right now (no debate)")
    for i, step in enumerate(out["do_now"], start=1):
        st.write(f"{i}. {step}")

    st.divider()
    st.subheader("Lock-in")
    lock_action = st.text_input("First action you will complete in the next 48 hours", max_chars=120)
    when = st.text_input("When will you do it? (date/time)", placeholder="e.g. Today 3pm", max_chars=60)

    if st.button("Lock decision 🔒"):
        if not lock_action.strip() or not when.strip():
            st.error("Both fields required.")
        else:
            st.success("Locked. Stop thinking. Start acting.")
            st.caption(datetime.now().strftime("%Y-%m-%d %H:%M"))
            st.write(f"**Committed action:** {lock_action}")
            st.write(f"**When:** {when}")
