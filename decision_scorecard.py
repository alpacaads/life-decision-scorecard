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
    st.session_state.mirror = None
    st.session_state.mirror_correction = ""
    st.session_state.show_mirror_correction = False

    st.session_state.action = None
    st.session_state.action_correction = ""
    st.session_state.show_action_correction = False
    st.session_state.action_agreed = False
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
def ai_mirror(answers, correction=None):
    system = (
        "You are a blunt, calm decision mirror.\n"
        "Rules:\n"
        "- Speak directly to 'You'. Never say 'user'.\n"
        "- Plain text only. No HTML, markdown, or symbols.\n"
        "- Return JSON only with keys: want, act, dont, blocker.\n"
        "- Each value: 1 sentence, max 22 words.\n"
        "- Be precise, not motivational.\n"
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
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload)},
        ],
    )
    return json.loads(r.choices[0].message.content)


def ai_next_step(answers, mirror, correction=None):
    system = (
        "You are an execution coach.\n"
        "Rules:\n"
        "- Speak directly to 'You'.\n"
        "- Plain text only.\n"
        "- Return JSON only with keys:\n"
        "headline, action, steps, minutes, fits_10, why\n"
        "- steps: 3–5 bullet points, concise.\n"
        "- minutes must be 10, 15, 20, 30, 45, or 60.\n"
        "- Decide honestly if this can be done in 10 minutes.\n"
    )

    payload = {
        "decision": answers["decision"],
        "mirror": mirror,
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
# STEP 1–6 (inputs)
# ---------------------
steps = [
    ("decision", "What decision are You making?", "One sentence."),
    ("why_matters", "Why does this decision matter to You?", "One blunt paragraph."),
    ("why_not_yet", "Why haven’t You done it yet?", "Be honest."),
    ("if_dont", "What happens if You don’t do it?", "3–12 months ahead."),
    ("if_do", "What happens if You do it now?", "What improves."),
]

if st.session_state.step < 5:
    key, title, hint = steps[st.session_state.step]
    st.subheader(title)
    val = st.text_area("", value=need(key), placeholder=hint, height=120)
    setv(key, val)

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.session_state.step > 0 and st.button("⬅ Back"):
            go(st.session_state.step - 1)
    with b2:
        if st.button("Next ➜"):
            if not val.strip():
                st.error("Please answer before continuing.")
            else:
                go(st.session_state.step + 1)

elif st.session_state.step == 5:
    st.subheader("What are the 3 things You value most right now?")
    setv("value_1", st.text_input("Most important", need("value_1")))
    setv("value_2", st.text_input("Second", need("value_2")))
    setv("value_3", st.text_input("Third", need("value_3")))

    if st.button("Next ➜"):
        if not all([need("value_1"), need("value_2"), need("value_3")]):
            st.error("Fill all three.")
        else:
            go(6)

# ---------------------
# STEP 7 — Verdict
# ---------------------
elif st.session_state.step == 6:
    if not st.session_state.mirror:
        with st.spinner("Thinking clearly…"):
            st.session_state.mirror = ai_mirror(st.session_state.answers)

    m = st.session_state.mirror

    st.markdown(
        f"""
        <div style="border:1px solid rgba(255,255,255,0.12);
        border-radius:16px;padding:28px;background:rgba(255,255,255,0.03)">
        <div style="text-align:center;font-size:0.8rem;opacity:0.6;letter-spacing:0.12em;margin-bottom:14px;">
        VERDICT
        </div>
        <p><strong>What You want:</strong> {safe_text(m['want'])}</p>
        <p><strong>If You act:</strong> {safe_text(m['act'])}</p>
        <p><strong>If You don’t:</strong> {safe_text(m['dont'])}</p>
        <p><strong>What’s really stopping You:</strong> {safe_text(m['blocker'])}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    b1, b2, b3 = st.columns([1, 2, 2])
    with b1:
        if st.button("⬅ Back"):
            go(5)
    with b2:
        if st.button("Yes, you got that right"):
            go(7)
    with b3:
        if st.button("No, not exactly"):
            st.session_state.show_mirror_correction = True

    if st.session_state.show_mirror_correction:
        corr = st.text_area("What did I miss?", max_chars=200)
        if st.button("Redo"):
            with st.spinner("Reframing…"):
                st.session_state.mirror = ai_mirror(
                    st.session_state.answers, correction=corr
                )
            st.session_state.show_mirror_correction = False
            st.rerun()

# ---------------------
# STEP 8 — Next action
# ---------------------
elif st.session_state.step == 7:
    if not st.session_state.action:
        with st.spinner("Finding the clearest move…"):
            st.session_state.action = ai_next_step(
                st.session_state.answers, st.session_state.mirror
            )

    a = st.session_state.action

    st.subheader("Next best step")

    st.markdown(f"**{safe_text(a['headline'])}**")
    st.markdown(f"### {safe_text(a['action'])}")

    if a["fits_10"]:
        st.info("Good news: You can complete this in the next **10 minutes** if you decide to lock in.")
    else:
        st.info(f"This will take about **{a['minutes']} minutes** once you lock in.")

    st.markdown("### Do it like this:")
    for s in a["steps"]:
        st.markdown(f"- {safe_text(s)}")

    st.caption(safe_text(a["why"]))

    c1, c2 = st.columns([1, 1])
    if c1.button("Yes, I agree"):
        st.session_state.action_agreed = True
    if c2.button("Not exactly"):
        st.session_state.show_action_correction = True

    if st.session_state.show_action_correction:
        corr = st.text_area("What needs adjusting?")
        if st.button("Adjust"):
            with st.spinner("Adjusting…"):
                st.session_state.action = ai_next_step(
                    st.session_state.answers,
                    st.session_state.mirror,
                    correction=corr,
                )
            st.session_state.show_action_correction = False
            st.rerun()

    if st.session_state.action_agreed:
        st.divider()
        if st.button("Lock in now 🔒"):
            st.session_state.timer_start = time.time()
            go(8)
        if st.button("Maybe later"):
            st.session_state.did_it = False
            go(8)

# ---------------------
# STEP 9 — Outcome
# ---------------------
elif st.session_state.step == 8:
    if st.session_state.timer_start:
        elapsed = int(time.time() - st.session_state.timer_start)
        action = st.session_state.action
remaining = max(0, action["minutes"] * 60 - elapsed)
        st_autorefresh(interval=1000, key="tick")
        st.markdown(f"⏳ **{remaining//60:02d}:{remaining%60:02d} remaining**")

        if st.button("I did it"):
            st.success("Good. You acted. That’s how momentum is built.")
        if st.button("I didn’t do it"):
            st.info("That’s fine. It simply doesn’t matter enough right now.")

    if st.button("Run another decision"):
        reset_all()
