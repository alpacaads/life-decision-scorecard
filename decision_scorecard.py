import json
import time
import streamlit as st
from openai import OpenAI

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
    st.session_state.mirror_approved = False
    st.session_state.correction = ""
    st.session_state.action_one = None
    st.session_state.timer_started_at = None
    st.session_state.did_it = None

# -----------------------
# AI
# -----------------------
def ai_mirror(answers: dict, correction: str | None = None) -> dict:
    """
    Returns JSON:
    {
      "mirror": "short blunt mirror (max 5 lines)",
      "because": "one line: why You care",
      "blocker": "one line: why You haven't acted"
    }
    """
    system = (
        "You are a blunt, practical mirror. No therapy. No motivational tone. No fluff. "
        "Never say the word 'user'. Speak directly to 'You'. "
        "Return ONLY valid JSON with keys: mirror, because, blocker. "
        "mirror must be max 5 short lines. No bullet points."
    )

    payload = {
        "decision": answers.get("decision", ""),
        "why_matters": answers.get("why_matters", ""),
        "why_not_yet": answers.get("why_not_yet", ""),
        "if_dont": answers.get("if_dont", ""),
        "if_do": answers.get("if_do", ""),
        "values_top3": answers.get("values_top3", ""),
        "correction_if_any": correction or None,
        "format_instruction": (
            "Write the mirror in this exact structure:\n"
            "1) You want ___\n"
            "2) This matters because ___\n"
            "3) If You don’t act: ___\n"
            "4) If You act now: ___\n"
            "5) You haven’t acted because ___"
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
        "Do NOT give multiple steps. Do NOT give options. Do NOT give a plan."
    )

    payload = {
        "decision": answers.get("decision", ""),
        "mirror": mirror_obj.get("mirror", ""),
        "because": mirror_obj.get("because", ""),
        "blocker": mirror_obj.get("blocker", ""),
        "why_matters": answers.get("why_matters", ""),
        "why_not_yet": answers.get("why_not_yet", ""),
        "if_dont": answers.get("if_dont", ""),
        "if_do": answers.get("if_do", ""),
        "values_top3": answers.get("values_top3", ""),
        "hard_constraints": [
            "Must be doable with a laptop/phone right now.",
            "Must be specific (send X, write Y, book Z, open A and do B).",
            "Must not require waiting on other people to begin.",
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

# -----------------------
# State init
# -----------------------
if "step" not in st.session_state:
    st.session_state.step = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "mirror" not in st.session_state:
    st.session_state.mirror = None
if "mirror_approved" not in st.session_state:
    st.session_state.mirror_approved = False
if "correction" not in st.session_state:
    st.session_state.correction = ""
if "action_one" not in st.session_state:
    st.session_state.action_one = None
if "timer_started_at" not in st.session_state:
    st.session_state.timer_started_at = None
if "did_it" not in st.session_state:
    st.session_state.did_it = None

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
# Step 6: Values top 3
# -----------------------
elif st.session_state.step == 5:
    st.subheader("To help me make this decision, I need a little bit of information about You.")
    st.write("What are the **3 things** You value the most right now?")

    val = st.text_area(
        "",
        value=need("values_top3"),
        placeholder="e.g. Family, business stability, peace of mind",
        max_chars=220,
        height=110,
    )
    setv("values_top3", val)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("⬅ Back"):
            go(4)
    with c2:
        if st.button("Next ➜"):
            if not need("values_top3"):
                st.error("List 3 things (comma-separated is fine).")
            else:
                # clear downstream caches if they exist
                st.session_state.mirror = None
                st.session_state.mirror_approved = False
                st.session_state.action_one = None
                st.session_state.timer_started_at = None
                st.session_state.did_it = None
                go(6)

# -----------------------
# Step 7: AI Mirror + Confirm / Adjust
# -----------------------
elif st.session_state.step == 6:
    st.subheader("So what You’re saying is:")

    if st.session_state.mirror is None:
        with st.spinner("Thinking…"):
            st.session_state.mirror = ai_mirror(st.session_state.answers)

    m = st.session_state.mirror or {}

    if m:
        st.markdown(m.get("mirror", "").strip())
        st.divider()
        st.caption(f"**This matters because:** {m.get('because','').strip()}")
        st.caption(f"**You haven’t acted because:** {m.get('blocker','').strip()}")

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("⬅ Back"):
            st.session_state.mirror = None
            go(5)
    with c2:
        if st.button("Confirm ✅"):
            st.session_state.mirror_approved = True
            go(7)
    with c3:
        if st.button("Adjust ✍️"):
            st.session_state._show_correction = True
            st.rerun()

    if st.session_state.get("_show_correction"):
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
                        st.session_state.mirror = ai_mirror(st.session_state.answers, correction=st.session_state.correction)
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
    if a1:
        st.markdown(f"## {a1.get('one_thing','').strip()}")
        if a1.get("start"):
            st.caption(a1.get("start","").strip())

    # Start timer when this step first loads
    if st.session_state.timer_started_at is None:
        st.session_state.timer_started_at = time.time()

    total = 10 * 60
    elapsed = int(time.time() - st.session_state.timer_started_at)
    remaining = max(0, total - elapsed)

    mins = remaining // 60
    secs = remaining % 60

    st.divider()
    st.markdown(f"### ⏳ {mins:02d}:{secs:02d} remaining")

    # Live countdown
    st.autorefresh(interval=1000, key="timer_tick")

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("⬅ Back"):
            # Going back cancels timer + action so You can reconfirm mirror
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
