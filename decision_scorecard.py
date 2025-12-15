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
    txt = (txt or "").strip()
    return json.loads(txt)

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
    st.session_state._show_correction = False

    st.session_state.action_one = None
    st.session_state.action_correction = ""
    st.session_state._show_action_correction = False
    st.session_state.action_agreed = False
    st.session_state.lockin_started = False

    st.session_state.timer_started_at = None
    st.session_state.did_it = None

def verdict_box(m: dict):
    import html

    def clean(s: str) -> str:
        # Escape anything that could be treated like HTML
        return html.escape((s or "").strip())

    want = clean(m.get("want", ""))
    act = clean(m.get("act", ""))
    dont = clean(m.get("dont", ""))
    blocker = clean(m.get("blocker", ""))

    reflection = " ".join([x for x in [want, act, dont] if x]).strip()

    blocker_html = ""
    if blocker:
        blocker_html = f"""
        <div style="
            margin-top: 18px;
            display: inline-block;
            padding: 10px 14px;
            border-radius: 12px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.10);
            font-weight: 650;
            line-height: 1.65;
        ">
            {blocker}
        </div>
        """

    st.markdown(
        f"""
        <style>
            @keyframes lockinFadeUp {{
                from {{ opacity: 0; transform: translateY(10px); }}
                to   {{ opacity: 1; transform: translateY(0); }}
            }}
            .lockin-verdict {{
                animation: lockinFadeUp 320ms ease-out;
            }}
        </style>

        <div class="lockin-verdict" style="
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 18px;
            padding: 36px 40px;
            background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(255,255,255,0.015));
            box-shadow: 0 14px 40px rgba(0,0,0,0.4);
            text-align: center;
        ">
            <div style="
                font-size:0.75rem;
                opacity:0.55;
                letter-spacing:0.14em;
                margin-bottom:20px;
            ">
                VERDICT
            </div>

            <div style="
                font-size:1.15rem;
                line-height:1.75;
                max-width: 680px;
                margin: 0 auto;
            ">
                {reflection}
                {blocker_html}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
# -----------------------
# AI
# -----------------------
def ai_mirror(answers: dict, correction: str | None = None) -> dict:
    """
    Returns JSON:
    {
      "want": "one blunt line",
      "act": "if You act now: impact on top values (one line)",
      "dont": "if You don't act: impact on top values (one line)",
      "blocker": "real reason You haven't acted + insight (one line)"
    }
    """
    system = (
        "You are a blunt, high-precision decision mirror. No fluff. No therapy. "
        "Never say the word 'user'. Speak directly to 'You'. "
        "Return ONLY valid JSON with keys: want, act, dont, blocker. "
        "Each value must be ONE sentence (max 22 words). "
        "You must reference the top values explicitly in act/dont. "
        "blocker must be insightful (not generic fear); tie it to what You said earlier. "
        "Do NOT moralise. Do NOT motivate. Be accurate and specific."
    )

    payload = {
        "decision": answers.get("decision", ""),
        "why_matters": answers.get("why_matters", ""),
        "why_not_yet": answers.get("why_not_yet", ""),
        "if_dont": answers.get("if_dont", ""),
        "if_do": answers.get("if_do", ""),
        "values_ranked": [
            answers.get("value_1", ""),
            answers.get("value_2", ""),
            answers.get("value_3", ""),
        ],
        "correction_if_any": correction or None,
        "instructions": (
            "Analyse all inputs deeply, then compress into four sharp lines:\n"
            "- want: what You’re trying to achieve\n"
            "- act: if You act now, what improves across the ranked values\n"
            "- dont: if You don’t act, what worsens across the ranked values\n"
            "- blocker: the real reason You haven’t acted, with a precise insight"
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

def ai_one_thing(answers: dict, mirror_obj: dict, correction: str | None = None) -> dict:
    """
    Returns JSON:
    {
      "headline": "good news line if <=10 mins, otherwise neutral",
      "action": "ONE concrete action",
      "start": "one short sentence to begin",
      "minutes": 10|15|20|30|45|60,
      "why_this": "one tight sentence why this is the next best step"
    }
    """
    system = (
        "You are a blunt execution coach. No fluff. No hedging. "
        "Never say the word 'user'. Speak directly to 'You'. "
        "Return ONLY valid JSON with keys: headline, action, start, minutes, why_this. "
        "action must be ONE concrete action that can be started immediately. "
        "minutes must be one of: 10, 15, 20, 30, 45, 60. "
        "Decide honestly if the best next step fits 10 minutes; if yes, headline must frame it as good news. "
        "If not, headline should be neutral but decisive. "
        "If correction_if_any is present, adjust the action accordingly."
    )

    payload = {
        "decision": answers.get("decision", ""),
        "why_matters": answers.get("why_matters", ""),
        "why_not_yet": answers.get("why_not_yet", ""),
        "if_dont": answers.get("if_dont", ""),
        "if_do": answers.get("if_do", ""),
        "values_ranked": [
            answers.get("value_1", ""),
            answers.get("value_2", ""),
            answers.get("value_3", ""),
        ],
        "mirror": mirror_obj,
        "correction_if_any": correction or None,
        "constraints": [
            "Give ONE action only (no multi-step plan).",
            "Must not require waiting on someone else to begin.",
            "Must reduce the main blocker immediately.",
            "Prefer actions that create a real artifact: sent message, drafted email, booked meeting, written doc, created proposal, etc."
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
if "correction" not in st.session_state:
    st.session_state.correction = ""
if "_show_correction" not in st.session_state:
    st.session_state._show_correction = False

if "action_one" not in st.session_state:
    st.session_state.action_one = None
if "action_correction" not in st.session_state:
    st.session_state.action_correction = ""
if "_show_action_correction" not in st.session_state:
    st.session_state._show_action_correction = False
if "action_agreed" not in st.session_state:
    st.session_state.action_agreed = False
if "lockin_started" not in st.session_state:
    st.session_state.lockin_started = False

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

# Step 1: Decision
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

# Step 2: Why it matters
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

# Step 3: Why not yet
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

# Step 4: If you don’t
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

# Step 5: If you do now
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

# Step 6: Values top 3 (separate fields)
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

                st.session_state.action_correction = ""
                st.session_state._show_action_correction = False
                st.session_state.action_agreed = False
                st.session_state.lockin_started = False

                go(6)

# Step 7: Verdict + confirm/adjust (new button text)
elif st.session_state.step == 6:
    if st.session_state.mirror is None:
        with st.spinner("Thinking…"):
            st.session_state.mirror = ai_mirror(st.session_state.answers)

    m = st.session_state.mirror or {}
    verdict_box(m)

    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        if st.button("⬅ Back"):
            st.session_state.mirror = None
            go(5)
    with c2:
        if st.button("Yes, you got that right"):
            # reset Step 8 state
            st.session_state.action_one = None
            st.session_state.action_correction = ""
            st.session_state._show_action_correction = False
            st.session_state.action_agreed = False
            st.session_state.lockin_started = False
            st.session_state.timer_started_at = None
            st.session_state.did_it = None
            go(7)
    with c3:
        if st.button("No, not exactly"):
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
            if st.button("Redo verdict ➜"):
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

# Step 8: Next step (Agree/Adjust) -> Lock in now / Maybe later -> Timer
elif st.session_state.step == 7:
    st.subheader("Next best step")

    if st.session_state.action_one is None:
        with st.spinner("Choosing the next best step…"):
            st.session_state.action_one = ai_one_thing(
                st.session_state.answers,
                st.session_state.mirror or {}
            )

    a = st.session_state.action_one or {}
    headline = (a.get("headline", "") or "").strip()
    action = (a.get("action", "") or "").strip()
    start_line = (a.get("start", "") or "").strip()
    why_this = (a.get("why_this", "") or "").strip()

    minutes = int(a.get("minutes", 10) or 10)
    minutes = minutes if minutes in [10, 15, 20, 30, 45, 60] else 10

    # Phase A: propose + agree/adjust
    if not st.session_state.action_agreed:
        if headline:
            st.markdown(f"### {headline}")
        if action:
            st.markdown(f"## {action}")
        if start_line:
            st.caption(start_line)
        if why_this:
            st.divider()
            st.caption(why_this)

        st.divider()
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button("⬅ Back"):
                st.session_state.action_one = None
                st.session_state.action_correction = ""
                st.session_state._show_action_correction = False
                go(6)
        with c2:
            if st.button("Yes, I agree ✅"):
                st.session_state.action_agreed = True
                st.rerun()
        with c3:
            if st.button("Not exactly"):
                st.session_state._show_action_correction = True
                st.rerun()

        if st.session_state._show_action_correction:
            corr = st.text_area(
                "What’s not quite right? (one blunt correction)",
                value=st.session_state.action_correction,
                max_chars=240,
                height=90,
            )
            st.session_state.action_correction = (corr or "").strip()

            cc1, cc2 = st.columns([1, 1])
            with cc1:
                if st.button("Cancel"):
                    st.session_state._show_action_correction = False
                    st.rerun()
            with cc2:
                if st.button("Adjust the step ➜"):
                    if not st.session_state.action_correction:
                        st.error("Write a correction first.")
                    else:
                        with st.spinner("Adjusting…"):
                            st.session_state.action_one = ai_one_thing(
                                st.session_state.answers,
                                st.session_state.mirror or {},
                                correction=st.session_state.action_correction
                            )
                        st.session_state._show_action_correction = False
                        st.rerun()

    # Phase B: choose Lock In now vs Maybe later
    elif not st.session_state.lockin_started:
        st.markdown("### Ready?")
        st.markdown(f"**Time box:** {minutes} minutes")
        st.markdown(f"**Action:** {action}")

        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            if st.button("⬅ Back"):
                st.session_state.action_agreed = False
                st.rerun()
        with c2:
            if st.button("Lock in now 🔒"):
                st.session_state.lockin_started = True
                st.session_state.timer_started_at = time.time()
                st.rerun()
        with c3:
            if st.button("Maybe later"):
                st.session_state.did_it = False
                go(8)

    # Phase C: timer running
    else:
        st.subheader("Lock In 🔒")
        if action:
            st.markdown(f"## {action}")
        if start_line:
            st.caption(start_line)

        total = minutes * 60
        elapsed = int(time.time() - (st.session_state.timer_started_at or time.time()))
        remaining = max(0, total - elapsed)

        mins = remaining // 60
        secs = remaining % 60

        st.divider()
        st.markdown(f"### ⏳ {mins:02d}:{secs:02d} remaining")

        st_autorefresh(interval=1000, key="timer_tick")

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("I did it ✅"):
                st.session_state.did_it = True
                go(8)
        with c2:
            if st.button("I didn’t do it"):
                st.session_state.did_it = False
                go(8)

# Step 9: Outcome
elif st.session_state.step == 8:
    if st.session_state.did_it is True:
        st.success("Good. You acted. That’s how You get closer to what You said matters.")
        st.caption("If You want momentum: do the next smallest step immediately.")
    else:
        st.info("That’s fine. It simply means this doesn’t matter to You right now. Revisit it when it becomes urgent.")

    st.divider()
    if st.session_state.action_one and st.session_state.action_one.get("action"):
        st.caption(f"Last action: {st.session_state.action_one.get('action')}")

    if st.button("Run another decision ➜"):
        reset_all()
        go(0)
