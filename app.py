from __future__ import annotations

import uuid
import base64
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from core.config import load_config
from core.logging_setup import setup_logger
from core.llm_factory import create_llm
from core.orchestrator import generate_only, generate_and_improve, improve_again
from agent.schemas import PoemRequest
from core.storage import get_storage

# -------------------------------------------------
# Setup
# -------------------------------------------------

load_dotenv()
logger = setup_logger()

st.set_page_config(page_title="The Weight of Words", page_icon="📜", layout="wide")

# -------------------------------------------------
# Background + Fonts
# -------------------------------------------------


def inject_theme(bg_path: Path) -> None:
    encoded = base64.b64encode(bg_path.read_bytes()).decode("utf-8")
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/jpg;base64,{encoded}");
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }}

        .stApp::before {{
            content: "";
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.25);
            pointer-events: none;
            z-index: 0;
        }}

        .stApp > div {{
            position: relative;
            z-index: 1;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


BG_PATH = Path(__file__).parent / "assets" / "background.jpg"
if BG_PATH.exists():
    inject_theme(BG_PATH)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap');

    .title-text {
        font-family: 'Great Vibes', cursive;
        font-size: 72px;
        font-weight: 400;
        text-align: center;
        margin: 0.15em 0 0.05em 0;
    }

    .subtitle-text {
        text-align: center;
        font-size: 1.1rem;
        opacity: 0.85;
        margin-bottom: 1.25rem;
    }
    </style>

    <div class="title-text">The Weight of Words</div>
    <div class="subtitle-text">Beautiful poem generator</div>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# Config
# -------------------------------------------------

try:
    cfg = load_config()
except Exception as e:
    st.error(str(e))
    st.stop()

# -------------------------------------------------
# Storage
# -------------------------------------------------

storage = get_storage()
try:
    storage.init()
except Exception as e:
    st.error(f"Storage init failed: {e}")
    st.stop()

if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

# -------------------------------------------------
# Writer styles
# -------------------------------------------------

WRITER_STYLES = {
    "Default": None,
    "William Shakespeare": "elevated lyrical drama, balanced cadence, rich metaphor",
    "Emily Dickinson": "compressed lines, sharp pauses, quiet intensity",
    "Walt Whitman": "expansive free verse, long lines, generous warmth",
    "Pablo Neruda": "sensuous imagery, emotional depth",
    "T.S. Eliot": "modernist precision, surprising imagery",
    "Langston Hughes": "musical cadence, plainspoken power",
    "Rumi": "spiritual metaphor, luminous simplicity",
    "Sylvia Plath": "intense imagery, emotional voltage",
    "Seamus Heaney": "earthy tactile imagery",
    "Matsuo Bashō": "minimalist stillness, nature clarity",
    "Alexander Pushkin": "lyrical clarity, narrative elegance",
}

# -------------------------------------------------
# Session state defaults
# -------------------------------------------------

for k in [
    "last_request",
    "last_poem",
    "last_critique",
    "last_revised",
    "versions",
    "poem_name",
    "rated_versions",
]:
    st.session_state.setdefault(k, None)

st.session_state.setdefault("versions", [])
st.session_state.setdefault("rated_versions", set())

st.session_state.setdefault("adv_model", "gpt-4o-mini")
st.session_state.setdefault("adv_temperature", 0.9)
st.session_state.setdefault("adv_top_p", 0.95)
st.session_state.setdefault("adv_audience", "")
st.session_state.setdefault("adv_apply_prefs", True)
st.session_state.setdefault("adv_use_people", True)
st.session_state.setdefault("adv_show_injected_memory", False)
st.session_state.setdefault("adv_rhyme", False)
st.session_state.setdefault("adv_no_cliches", True)
st.session_state.setdefault("adv_reading_level", "general")
st.session_state.setdefault("adv_must_include", "")
st.session_state.setdefault("adv_avoid", "")
st.session_state.setdefault("adv_syllable_hints", "")
st.session_state.setdefault("adv_tone", "warm")
st.session_state.setdefault("adv_show_debug", False)

STAR_OPTIONS = [1, 2, 3, 4, 5]

# -------------------------------------------------
# Helpers
# -------------------------------------------------


def stars_label(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


def build_user_memory(storage_obj, user_id, include_prefs, include_people) -> str:
    parts = []

    if include_prefs:
        taste = storage_obj.get_taste_profile(user_id) or {}
        if taste.get("total_ratings", 0):
            parts.append("Preferences learned from ratings.")

    if include_people:
        ppl = storage_obj.list_people(user_id) or []
        if ppl:
            parts.append(
                "People memory:\n"
                + "\n".join(f"- {p['name']} ({p['relationship']})" for p in ppl[:10])
            )

    return "\n\n".join(parts) or "None"


# -------------------------------------------------
# Tabs
# -------------------------------------------------

tabs = st.tabs(["Write", "People", "Advanced"])

# -------------------------------------------------
# LLM
# -------------------------------------------------

llm = create_llm(
    cfg,
    model=st.session_state["adv_model"],
    temperature=st.session_state["adv_temperature"],
    top_p=st.session_state["adv_top_p"],
)

# -------------------------------------------------
# WRITE TAB (unchanged logic)
# -------------------------------------------------

with tabs[0]:
    st.subheader("Write")

    user_memory = build_user_memory(
        storage,
        USER_ID,
        st.session_state["adv_apply_prefs"],
        st.session_state["adv_use_people"],
    )

    if st.session_state["adv_show_injected_memory"]:
        st.code(user_memory)

    poem_name = st.text_input(
        "Poem name", value=st.session_state["poem_name"] or "Untitled"
    )
    st.session_state["poem_name"] = poem_name

    theme = st.text_area("Theme / Background", height=120)

    writer_style = st.selectbox("Writer style", list(WRITER_STYLES.keys()))
    style = st.selectbox(
        "Format",
        ["free_verse", "haiku", "limerick", "acrostic", "sonnet_like", "spoken_word"],
    )

    line_count = st.slider("Length (lines)", 2, 60, 12)

    req = PoemRequest(
        occasion="for inspiration",
        theme=theme or "a meaningful moment",
        audience=st.session_state["adv_audience"] or None,
        style=style,
        tone=st.session_state["adv_tone"],
        writer_vibe=WRITER_STYLES[writer_style],
        must_include=[],
        avoid=[],
        line_count=line_count,
        rhyme=st.session_state["adv_rhyme"],
        syllable_hints=None,
        no_cliches=st.session_state["adv_no_cliches"],
        reading_level=st.session_state["adv_reading_level"],
        acrostic_word=None,
    )

    if st.button("Generate"):
        out = generate_only(llm, req, user_memory=user_memory)
        if out.ok:
            st.session_state["versions"] = [{"label": "Version 1", "text": out.poem}]
        else:
            st.error(out.error_user)

    for v in st.session_state["versions"]:
        st.markdown(f"### {v['label']}")
        st.code(v["text"])
