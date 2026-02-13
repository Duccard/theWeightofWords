from __future__ import annotations

import uuid
import streamlit as st
from dotenv import load_dotenv

from core.config import load_config
from core.logging_setup import setup_logger
from core.llm_factory import create_llm
from core.orchestrator import generate_only, generate_and_improve, improve_again
from agent.schemas import PoemRequest
from core.storage import get_storage

load_dotenv()
logger = setup_logger()

# ---------- Page config ----------
st.set_page_config(page_title="The Weight of Words", page_icon=None, layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Dancing+Script:wght@600;700&display=swap');

h1 {
  font-family: 'Dancing Script', cursive !important;
  font-size: 3.2rem !important;
  margin-bottom: 0.2rem !important;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown("<h1>The Weight of Words</h1>", unsafe_allow_html=True)
st.caption(
    "Poem generator — quick writing on the Write tab, power controls in Advanced."
)

# ---------- Config ----------
try:
    cfg = load_config()
except Exception as e:
    st.error(str(e))
    st.stop()

# ---------- Storage ----------
storage = get_storage()
try:
    storage.init()
except Exception as e:
    st.error(f"Storage init failed: {e}")
    st.stop()

# ---------- User ----------
if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

# ---------- Session state ----------
for k in [
    "last_request",
    "last_poem",
    "last_critique",
    "last_revised",
    "versions",
    "poem_name",
    "rated_versions",
    "apply_prefs",
    "use_people",
    "show_injected_memory",
]:
    st.session_state.setdefault(k, None)

if st.session_state["versions"] is None:
    st.session_state["versions"] = []

if st.session_state["rated_versions"] is None:
    st.session_state["rated_versions"] = set()

st.session_state["apply_prefs"] = (
    True if st.session_state["apply_prefs"] is None else st.session_state["apply_prefs"]
)
st.session_state["use_people"] = (
    True if st.session_state["use_people"] is None else st.session_state["use_people"]
)
st.session_state["show_injected_memory"] = (
    False
    if st.session_state["show_injected_memory"] is None
    else st.session_state["show_injected_memory"]
)

# ---------- Helpers ----------
STAR_OPTIONS = [1, 2, 3, 4, 5]


def stars_label(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


def build_user_memory(
    storage_obj, user_id: str, include_prefs: bool, include_people: bool
) -> str:
    parts = []

    if include_prefs:
        taste = storage_obj.get_taste_profile(user_id) or {}
        total = int(taste.get("total_ratings", 0) or 0)
        if total <= 0:
            parts.append("Preferences learned from ratings: none yet.")
        else:
            parts.append(f"Preferences learned from ratings: {taste}")

    if include_people:
        ppl = storage_obj.list_people(user_id) or []
        if not ppl:
            parts.append("People memory: none yet.")
        else:
            lines = []
            for p in ppl[:10]:
                note = f" — note: {p['note']}" if p.get("note") else ""
                lines.append(f"- {p['name']} ({p['relationship']}){note}")
            parts.append("People memory:\n" + "\n".join(lines))

    return "\n\n".join(parts).strip() or "None"


# ---------- Tabs ----------
main_tabs = st.tabs(["Write", "People", "Advanced"])

# ================= ADVANCED =================
with main_tabs[2]:
    st.subheader("Advanced settings")

    st.markdown("### Memory injection")
    st.session_state["apply_prefs"] = st.toggle(
        "Apply my preferences", value=st.session_state["apply_prefs"]
    )
    st.session_state["use_people"] = st.toggle(
        "Use people memory", value=st.session_state["use_people"]
    )
    st.session_state["show_injected_memory"] = st.checkbox(
        "Show injected memory (debug)",
        value=st.session_state["show_injected_memory"],
    )

    st.divider()
    st.caption(f"Storage backend: **{storage.backend_name()}**")
    st.markdown("### Your taste profile")
    st.json(storage.get_taste_profile(USER_ID))

# ================= PEOPLE =================
with main_tabs[1]:
    st.subheader("People (memory)")

    with st.form("add_person_form", clear_on_submit=True):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship")
        note = st.text_area("Note (optional)")
        submitted = st.form_submit_button("Save")

    if submitted:
        storage.add_person(USER_ID, name=name, relationship=relationship, note=note)
        st.success("Saved.")

    st.divider()
    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")
    else:
        for p in people:
            st.markdown(f"**{p['name']}** — *{p['relationship']}*")
            if p.get("note"):
                st.caption(p["note"])

# ================= WRITE =================
with main_tabs[0]:
    st.subheader("Write")

    user_memory = build_user_memory(
        storage,
        USER_ID,
        include_prefs=st.session_state["apply_prefs"],
        include_people=st.session_state["use_people"],
    )

    if st.session_state["show_injected_memory"]:
        st.code(user_memory)

    poem_name = st.text_input(
        "Poem name", value=st.session_state.get("poem_name") or "Untitled"
    )
    st.session_state["poem_name"] = poem_name

    theme_bg = st.text_area("Theme / background", height=120)

    audience = st.text_input(
        "Audience",
        help="Who this poem is for (e.g. Dom, best friend, partner). Guides tone and references.",
    )

    tone = st.selectbox(
        "Tone", ["warm", "funny", "romantic", "hopeful", "somber", "surreal"]
    )
    style = st.selectbox("Format", ["free_verse", "haiku", "spoken_word"])
    line_count = st.slider("Length (lines)", 2, 60, 12)

    req = PoemRequest(
        occasion="for inspiration",
        theme=theme_bg,
        audience=audience,
        style=style,
        tone=tone,
        writer_vibe=None,
        must_include=[],
        avoid=[],
        line_count=line_count,
        rhyme=False,
        syllable_hints=None,
        no_cliches=True,
        reading_level="general",
        acrostic_word=None,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        btn_fast = st.button("Generate only")
    with col2:
        btn_full = st.button("Generate + Improve", type="primary")
    with col3:
        btn_again = st.button(
            "Improve again", disabled=not st.session_state["versions"]
        )

    if btn_fast:
        out = generate_only(llm=create_llm(cfg), req=req, user_memory=user_memory)
        if out.ok:
            st.session_state["versions"] = [{"label": "Version 1", "text": out.poem}]
            st.rerun()

    if btn_full:
        out = generate_and_improve(
            llm=create_llm(cfg), req=req, user_memory=user_memory
        )
        if out.ok:
            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
            ]
            st.rerun()

    if btn_again:
        base = st.session_state["versions"][-1]["text"]
        out = improve_again(create_llm(cfg), req, base, user_memory)
        if out.ok:
            st.session_state["versions"].append(
                {
                    "label": f"Version {len(st.session_state['versions'])+1} (Upgraded)",
                    "text": out.revised_poem,
                }
            )
            st.rerun()

    st.divider()
    for v in st.session_state["versions"]:
        st.markdown(f"### {v['label']}")
        st.code(v["text"])
