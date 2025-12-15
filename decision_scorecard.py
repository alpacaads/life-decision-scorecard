import json
import time
import re
import html
import streamlit as st
from openai import OpenAI
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title="Lock In", page_icon="🧭", layout="centered")

# =====================
# Helpers
# =====================
def get_client():
    return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])


def strip_tags(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("<", "").replace(">", "")
    return text.strip()


def safe_text(s: str) -> str:
    return html.escape(strip_tags(s))


def go(step: int):
    st.session_state.step = step
    st.rerun()


def reset_all():
    st.session_state.step = 0
    st.session_state.answers = {}

    st.session_state.analysis = None
    st.session_state.analysis_correction = ""
    st.session_state.show_analysis_correction = False

    st.session_state.decision_action = None
    st.session_state.action_correction = ""
    st.session_state.show_action_correction = False

    st.session_state.locked_in = False
    st.session_state.timer_start = None
    st.session_state.did_it = None


def need(k):
    return (st.session_state.answers.get(k, "") or "").strip()


def setv(k, v):
    st.session_state.answers[k] = (v or "").strip()


# =====================
# AI
# =====================
def ai_risk_reward(answers, correction=None):
    system = (
        "You are a calm, rational decision analyst.\n"
        "Speak directly to 'You'. Never say 'user'.\n"
        "Plain text only. No HTML, markdown, or symbols.\n"
        "Return JSON ONLY with keys:\n"
        "risk_reward\n"
        "The value must be a single, thoughtful paragraph explaining:\n"
        "- the upside if You act\n"
        "- the downside if You don't\n"
        "- the real tradeoff involved\n"
        "Do not give advice yet.\n"
    )

    payload = {
        "decision": answers["decision"],
        "why_matters": answers["why_matters"],
        "why_not_yet": answers["why_not_yet"],
        "if_dont": answers["if_dont"],
        "if_do": answers["if_do"],
        "values": [answers["value_1"], answers["value_2"], answers["value_3"]],
        "correction": correction,
    }

    r = get_client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.25,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return json.loads(r.choices[0].message.content)


def ai_one_action(answers, analysis, correction=None):
    system = (
        "You are an execution-focused decision guide.\n"
        "Speak directly to 'You'.\n"
        "Plain text only.\n"
        "Return JSON ONLY with keys:\n"
        "action, minutes\n"
        "Rules:\n"
        "- action must be ONE clear decision or action\n"
        "- no steps, no lists, no explanations\n"
        "- minutes must be one of: 10, 15, 20, 30, 45, 60\n"
        "- choose the smallest honest time needed\n"
    )

    payload = {
        "decision": answers["decision"],
        "analysis": analysis,
        "values": [answers["value_1"], answers["value_2"], answers["value_3"]],
        "correction": correction,
    }

    r = get_client().chat.completions.create(
        model="gpt-4.1-mini",
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return json.loads(r.choices[0].message.content)


# =====================
# State init
# =====================
if "step" not in st.session_state:
    reset_all()

# =====================
# UI
# =====================
st.title("Lock In 🧭")
st.caption("One question. One action. Ten minutes.")

c1, c2 = st.columns([1, 1])
with c1:
    if st.button("↩ Reset"):
        reset_all()
with c2:
    st.caption(f"Step {st.session_state.step + 1} / 9")

st.divider()

# ---------------------
# STEP 1–5 (inputs)
# ---------------------
steps = [
    ("decision", "What decision are You making?", "One sentence."),
    ("why_matters", "Why does this decision matter to You?", "Be direct."),
    ("why_not_yet", "Why haven’t You done it yet?", "Be honest."),
    ("if_dont", "What happens if You don’t do it?", "3–12 months ahead."),
    ("if_do", "And if You do it now, what happens?", "What improves."),
]

if st.session_state.step < 5:
    key, title, hint = steps[st.session_state.step]
    st.subheader(title)
    val = st.text_area("", value=need(key), placeholder=hint, height=120)
    setv(key, val)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.session_state.step > 0 and st.button("⬅ Back"):
            go(st.session_state.step - 1)
    with c2:
        if st.button("Next ➜"):
            if not val.strip():
                st.error("Please answer before continuing.")
            else:
                go(st.session_state.step + 1)

# ---------------------
# STEP 6 — Values
# ---------------------
elif st.session_state.step == 5:
    st.subheader("What are the 3 things You value most right now?")
    setv("value_1", st.text_input("Most important", need("value_1")))
    setv("value_2", st.text_input("Second", need("value_2")))
    setv("value_3", st.text_input("Third", need("value_3")))

    if st.button("Next ➜"):
        if not all([need("value_1"), need("value_2"), need("value_3")]):
            st.error("Fill all three.")
        else:
            st.session_state.analysis = None
            st.session_state.decision_action = None
            go(6)

# ---------------------
# STEP 7 — Risk & Reward Analysis
# ---------------------
elif st.session_state.step == 6:
    if not st.session_state.analysis:
        with st.spinner("Weighing the tradeoff…"):
            st.session_state.analysis = ai_risk_reward(st.session_state.answers)

    analysis_text = safe_text(st.session_state.analysis["risk_reward"])

    st.markdown(
        f"""
        <div style="
            border:1px solid rgba(255,255,255,0.12);
            border-radius:16px;
            padding:32px 36px;
            background:linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.01));
            box-shadow:0 12px 34px rgba(0,0,0,0.38);
        ">
            <div style="text-align:center;font-size:0.8rem;opacity:0.6;letter-spacing:0.12em;margin-bottom:18px;">
                RISK & REWARD ANALYSIS
            </div>
            <div style="font-size:1.05rem;line-height:1.75;">
                {analysis_text}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("⬅ Back"):
            go(5)
    with c2:
        if st.button("Continue"):
            go(7)

# ---------------------
# STEP 8 — One action
# ---------------------
elif st.session_state.step == 7:
    if not st.session_state.decision_action:
        with st.spinner("Finding the one move that matters…"):
            st.session_state.decision_action = ai_one_action(
                st.session_state.answers,
                st.session_state.analysis["risk_reward"],
            )

    action = st.session_state.decision_action
    minutes = int(action["minutes"])

    st.subheader("The one thing to do now")
    st.markdown(f"### {safe_text(action['action'])}")
    st.caption(f"This takes about {minutes} minutes once You lock in.")

    st.divider()
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Lock in 🔒"):
            st.session_state.locked_in = True
            st.session_state.timer_start = time.time()
            go(8)
    with c2:
        if st.button("Not right now"):
            st.session_state.did_it = False
            go(8)

# ---------------------
# STEP 9 — Timer & outcome
# ---------------------
elif st.session_state.step == 8:
    action = st.session_state.decision_action
    minutes = int(action["minutes"])

    if st.session_state.timer_start:
        elapsed = int(time.time() - st.session_state.timer_start)
        remaining = max(0, minutes * 60 - elapsed)

        st_autorefresh(interval=1000, key="tick")
        st.markdown(f"⏳ **{remaining//60:02d}:{remaining%60:02d} remaining**")

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("I did it"):
                st.session_state.did_it = True
        with c2:
            if st.button("I didn’t do it"):
                st.session_state.did_it = False

    if st.session_state.did_it is True:
        st.success("Good. You acted. That’s how momentum is built.")
    elif st.session_state.did_it is False:
        st.info("That’s fine. It simply means this doesn’t matter to You right now.")

    if st.button("Run another decision"):
        reset_all()
