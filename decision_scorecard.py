import json
import time
import streamlit as st
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Lock In", page_icon="🧭", layout="centered")

# -----------------------
# Helpers
# -----------------------
def get_client():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

def safe_json_loads(txt: str):
    return json.loads((txt or "").strip())

def need(key: str) -> str:
    return (st.session_state.answers.get(key, "") or "").strip()

def setv(key: str, val: str):
    st.session_state.answers[key] = (val or "").strip()

def go(step: int):
    st.session_state.step = step
    st.rerun()

def reset_all():
    st.session_state.step = 0
    st.session_state.answers = {}
    st.session_state.mirror = None
    st.session_state.correction = ""
    st.session_state.action_one = None
    st.session_state.timer_started_at = None
    st.session_state.did_it = None
    st.session_state._show_correction = False

# -----------------------
# AI
# -----------------------
def ai_mirror(answers: dict, correction: str | None = None) -> dict:
    """
    Returns JSON:
    {
      "mirror": "2–3 sentences max, blunt, thoughtful",
      "because": "",
      "blocker": ""
    }
    """
    system = (
        "You are a blunt, high-precision decision mirror. No fluff. No therapy. "
        "Never say the word 'user'. Speak directly to 'You'. "
        "Return ONLY valid JSON with keys: mirror, because, blocker. "
        "IMPORTANT: mirror must be 2–3 sentences MAX. No bullet points. "
        "mirror must explicitly reference the top values and the impact on them. "
        "mirror must include ONE sharp insight about why You haven’t acted, tied to the values/outcomes. "
        "Avoid generic phrasing like 'this matters because' unless it adds new information."
    )

    payload = {
        "decision": answers.get("decision", ""),
        "why_matters": answers.get("why_matters", ""),
        "why_not_yet": answers.get("why_not_yet", ""),
        "if_dont": answers.get("if_dont", ""),
        "if_do": answers.get("if_do", ""),
        "values_top3_ranked": [
            answers.get("value_1", ""),
            answers.get("value_2", ""),
            answers.get("value_3", ""),
        ],
        "values_top3_combined": answers.get("values_top3", ""),
        "correction_if_any": correction or None,
        "output_style": (
            "Write it like this, but keep it 2–3 sentences:\n"
            "So what I’m getting is: if You do this, the impact on [top values] is ___. "
            "You haven’t done it because ___. The real issue is ___."
        ),
    }

    resp = get_client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return safe_json_loads(resp.choices[0].message.content)

def ai_one_thing(answers: dict, mirror_obj: dict) -> dict:
    """
    Returns JSON:
    {
      "one_thing": "ONE specific action for next 10 minutes",
      "start": "one short sentence telling You how to start"
    }
    """
    system = (
        "You are a blunt execution coach. No fluff. No hedging. "
        "Never say the word 'user'. Speak directly to 'You'. "
        "Return ONLY valid JSON with keys: one_thing, start. "
        "one_thing must be ONE concrete action You can start immediately and make progress on in 10 minutes. "
        "Do NOT give multiple steps. Do NOT give options. Do NOT give a plan. "
        "Make it specific and startable right now."
    )

    payload = {
        "decision": answers.get("decision", ""),
        "mirror": mirror_obj.get("mirror", ""),
        "why_matters": answers.get("why_matters", ""),
        "why_not_yet": answers.get("why_not_yet", ""),
        "if_dont": answers.get("if_dont", ""),
        "if_do": answers.get("if_do", ""),
        "values_top3_ranked": [
            answers.get("value_1", ""),
            answers.get("value_2", ""),
            answers.get("value_3", ""),
        ],
        "hard_constraints": [
            "Must be doable with a laptop/phone right now.",
            "Must be specific (send X, write Y, book Z, open A and do B).",
            "Must not require waiting on other people to begin.",
            "Should reduce the main blocker immediately (even if it’s only the first 10%).",
        ],
    }

    resp = get_client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return safe_json_loads(resp.choices[0].message.content)
def verdict_box(text: str):
    st.markdown(
        f"""
        <div style="
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 14px;
            padding: 28px 32px;
            background: linear-gradient(
                180deg,
                rgba(255,255,255,0.04),
                rgba(255,255,255,0.01)
            );
            box-shadow: 0 10px 30px rgba(0,0,0,0.35);
            font-size: 1.15rem;
            line-height: 1.6;
        ">
            <strong style="display:block; font-size:0.85rem; opacity:0.6; letter-spacing:0.08em; margin-bottom:10px;">
                VERDICT
            </strong>
            {text}
        </div>
        """,
        unsafe_allow_html=True
    )
# -----------------------
# State init
# -----------------------
if "step" not in st.session_state:
    st.session_state.step = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "mirror" not in st.session_state:
    st.session_state.mirror = None
if "correction" not in st.session_state:
    st.session_state.correction = ""
if "action_one" not in st.session_state:
    st.session_state.action_one = None
if "timer_started_at" not in st.session_state:
    st.session_state.timer_started_at = None
if "did_it" not in st.session_state:
    st.session_state.did_it = None
if "_show_correction" not in st.session_state:
    st.session_state._show_correction = False

# -----------------------
# UI
# -----------------------
st.title("Lock In 🧭")
st.caption("One question. One action. Ten minutes.")

topL, topR = st.columns([1, 1])
with topL:
    if st.button("↩ Reset"):
        reset_all()
with topR:
    st.caption(f"Step {st.session_state.step + 1} / 9")

st.divider()

# -----------------------
# Step 1: Decision
# -----------------------
if st.session_state.step == 0:
    st.subheader("What decision are You making?")
    val = st.text_input(
        "",
        value=need("decision"),
        placeholder="One sentence.",
        max_chars=140,
    )
    setv("decision", val)

    if st.button("Next ➜"):
        if not need("decision"):
            st.error("Write the decision in one sentence.")
        else:
            go(1)

# -----------------------
# Step 2: Why it matters
# -----------------------
elif st.session_state.step == 1:
    st.subheader("Tell me why this decision matters to You.")
    val = st.text_area(
        "",
        value=need("why_matters"),
        placeholder="One blunt paragraph.",
        max_chars=320,
        height=120,
    )
    setv("why_matters", val)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go(0)
    with c2:
        if st.button("Next ➜"):
            if not need("why_matters"):
                st.error("Write one short paragraph.")
            else:
                go(2)

# -----------------------
# Step 3: Why not yet
# -----------------------
elif st.session_state.step == 2:
    st.subheader("Why haven’t You done it yet?")
    val = st.text_area(
        "",
        value=need("why_not_yet"),
        placeholder="Be honest. One paragraph.",
        max_chars=320,
        height=120,
    )
    setv("why_not_yet", val)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go(1)
    with c2:
        if st.button("Next ➜"):
            if not need("why_not_yet"):
                st.error("Write one short paragraph.")
            else:
                go(3)

# -----------------------
# Step 4: If you don’t
# -----------------------
elif st.session_state.step == 3:
    st.subheader("What happens if You don’t do it?")
    val = st.text_area(
        "",
        value=need("if_dont"),
        placeholder="In 3–12 months, what gets worse?",
        max_chars=320,
        height=120,
    )
    setv("if_dont", val)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go(2)
    with c2:
        if st.button("Next ➜"):
            if not need("if_dont"):
                st.error("Write one short paragraph.")
            else:
                go(4)

# -----------------------
# Step 5: If you do now
# -----------------------
elif st.session_state.step == 4:
    st.subheader("And if You do it now, what happens?")
    val = st.text_area(
        "",
        value=need("if_do"),
        placeholder="What improves if You act this week?",
        max_chars=320,
        height=120,
    )
    setv("if_do", val)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go(3)
    with c2:
        if st.button("Next ➜"):
            if not need("if_do"):
                st.error("Write one short paragraph.")
            else:
                go(5)

# -----------------------
# Step 6: Values top 3 (separate fields)
# -----------------------
elif st.session_state.step == 5:
    st.subheader("To help me make this decision, I need a little bit of information about You.")
    st.write("What are the **3 things** You value the most right now?")

    v1 = st.text_input(
        "Most important",
        value=need("value_1"),
        placeholder="e.g. Spending time with my family",
        max_chars=80,
    )
    setv("value_1", v1)

    v2 = st.text_input(
        "Second most important",
        value=need("value_2"),
        placeholder="e.g. Stable income",
        max_chars=80,
    )
    setv("value_2", v2)

    v3 = st.text_input(
        "Third most important",
        value=need("value_3"),
        placeholder="e.g. Peace of mind",
        max_chars=80,
    )
    setv("value_3", v3)

    combined = ", ".join([x for x in [v1, v2, v3] if x.strip()])
    setv("values_top3", combined)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go(4)
    with c2:
        if st.button("Next ➜"):
            if not (v1.strip() and v2.strip() and v3.strip()):
                st.error("Please fill in all three values.")
            else:
                st.session_state.mirror = None
                st.session_state.action_one = None
                st.session_state.timer_started_at = None
                st.session_state.did_it = None
                st.session_state.correction = ""
                st.session_state._show_correction = False
                go(6)

# -----------------------
# Step 7: AI Mirror in a single callout box + Confirm / Adjust
# -----------------------
elif st.session_state.step == 6:
    st.subheader("So what You’re saying is:")

    if st.session_state.mirror is None:
        with st.spinner("Thinking…"):
            st.session_state.mirror = ai_mirror(st.session_state.answers)

    m = st.session_state.mirror or {}
    mirror_text = (m.get("mirror", "") or "").strip()

    if mirror_text:
        # Single callout box (feels like a verdict)
        verdict_box(mirror_text)

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("⬅ Back"):
            st.session_state.mirror = None
            go(5)
    with c2:
        if st.button("Confirm ✅"):
            go(7)
    with c3:
        if st.button("Adjust ✍️"):
            st.session_state._show_correction = True
            st.rerun()

    if st.session_state._show_correction:
        corr = st.text_area(
            "What did I get wrong? (one blunt correction)",
            value=st.session_state.correction,
            max_chars=240,
            height=90,
        )
        st.session_state.correction = (corr or "").strip()

        cc1, cc2 = st.columns([1, 1])
        with cc1:
            if st.button("Cancel"):
                st.session_state._show_correction = False
                st.rerun()
        with cc2:
            if st.button("Redo mirror ➜"):
                if not st.session_state.correction:
                    st.error("Write a correction first.")
                else:
                    with st.spinner("Rewriting…"):
                        st.session_state.mirror = ai_mirror(
                            st.session_state.answers,
                            correction=st.session_state.correction
                        )
                    st.session_state._show_correction = False
                    st.rerun()

# -----------------------
# Step 8: One thing + 10-minute timer + did/didn’t
# -----------------------
elif st.session_state.step == 7:
    st.subheader("Here’s what You should do in the next 10 minutes:")

    if st.session_state.action_one is None:
        with st.spinner("Choosing the one thing…"):
            st.session_state.action_one = ai_one_thing(st.session_state.answers, st.session_state.mirror or {})

    a1 = st.session_state.action_one or {}
    one_thing = (a1.get("one_thing", "") or "").strip()
    start_line = (a1.get("start", "") or "").strip()

    if one_thing:
        st.markdown(f"## {one_thing}")
    if start_line:
        st.caption(start_line)

    if st.session_state.timer_started_at is None:
        st.session_state.timer_started_at = time.time()

    total = 10 * 60
    elapsed = int(time.time() - st.session_state.timer_started_at)
    remaining = max(0, total - elapsed)

    mins = remaining // 60
    secs = remaining % 60

    st.divider()
    st.markdown(f"### ⏳ {mins:02d}:{secs:02d} remaining")

    # Live countdown refresh
    st_autorefresh(interval=1000, key="timer_tick")

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("⬅ Back"):
            st.session_state.action_one = None
            st.session_state.timer_started_at = None
            go(6)
    with c2:
        if st.button("I did it ✅"):
            st.session_state.did_it = True
            go(8)
    with c3:
        if st.button("I didn’t do it"):
            st.session_state.did_it = False
            go(8)

# -----------------------
# Step 9: Outcome
# -----------------------
elif st.session_state.step == 8:
    if st.session_state.did_it is True:
        st.success("Good. You improved Your life by acting. That’s how You get closer to what You said matters.")
        st.caption("If You want momentum: do the next smallest step immediately.")
    else:
        st.info("That’s fine. It simply means this doesn’t matter to You right now. Revisit it when it becomes urgent.")

    st.divider()
    if st.session_state.action_one and st.session_state.action_one.get("one_thing"):
        st.caption(f"Last 10-minute action: {st.session_state.action_one.get('one_thing')}")

    if st.button("Run another decision ➜"):
        reset_all()
        go(0)
