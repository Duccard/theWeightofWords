from __future__ import annotations

import uuid
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path
import base64

# --- CUSTOM IMPORTS ---
from core.config import load_config
from core.logging_setup import setup_logger
from core.llm_factory import create_llm
from core.orchestrator import generate_only, generate_and_improve, improve_again
from agent.schemas import PoemRequest
from core.storage import get_storage

load_dotenv()
logger = setup_logger()


def load_bg_image_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


st.set_page_config(page_title="The Weight of Words", page_icon="📜", layout="centered")
BG_PATH = Path(__file__).parent / "assets" / "background.jpg"
bg_base64 = load_bg_image_base64(BG_PATH)

# --- STYLING BLOCK ---
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap');

    .stApp {{
        background-image: url("data:image/jpeg;base64,{bg_base64}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    /* GLOBAL TEXT */
    html, body, .stApp, label, .stMarkdown, .stText,
    .stCaption, .stSubheader, .stHeader {{
        color: #ffffff !important;
    }}

    /* LEGIBILITY FIX FOR INFO/BLUE BOXES (No versions yet / No people yet) */
    div[data-testid="stNotification"] {{
        background-color: rgba(20, 20, 20, 0.85) !important;
        border: 1px solid #FF4B4B !important;
        border-radius: 10px;
    }}
    div[data-testid="stNotification"] p {{
        color: #ffffff !important;
    }}

    /* TITLE */
    .wow-title {{
        font-family: 'Great Vibes', cursive;
        font-size: 72px;
        text-align: center;
        color: #ffffff;
        margin-bottom: 0.2rem;
    }}

    /* SOLID RED PRIMARY BUTTONS (Generate+Improve, Save, Submit, Download) */
    /* Targeting by [kind="primary"] is the most reliable way to override transparency */
    button[kind="primary"] {{
        background-color: #FF4B4B !important;
        color: white !important;
        border: none !important;
        opacity: 1 !important;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.3) !important;
    }}

    button[kind="primary"]:hover {{
        background-color: #FF3333 !important;
        border: none !important;
    }}

    /* INPUT FIELDS */
    .stTextInput input, .stTextArea textarea, .stSelectbox div[role="combobox"] {{
        background: rgba(255,255,255,0.95) !important;
        color: #000000 !important;
        border-radius: 10px;
    }}
    </style>

    <div class="wow-title">The Weight of Words</div>
    <div class="wow-subtitle" style="text-align: center; color: white; opacity: 0.9; margin-bottom: 2rem;">Beautiful poem generator</div>
    """,
    unsafe_allow_html=True,
)

# --- APP LOGIC ---
try:
    cfg = load_config()
    storage = get_storage()
    storage.init()
except Exception as e:
    st.error(f"Init error: {e}")
    st.stop()

if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

# Defaults for Session State
defaults = {
    "adv_model": "gpt-4o-mini",
    "adv_temperature": 0.9,
    "adv_top_p": 0.95,
    "adv_audience": "",
    "adv_apply_prefs": True,
    "adv_use_people": True,
    "adv_show_injected_memory": False,
    "adv_rhyme": False,
    "adv_no_cliches": True,
    "adv_reading_level": "general",
    "adv_must_include": "",
    "adv_avoid": "",
    "adv_syllable_hints": "",
    "adv_tone": "warm",
    "adv_show_debug": False,
    "versions": [],
    "poem_name": "",
    "rated_versions": set(),
}
for key, val in defaults.items():
    st.session_state.setdefault(key, val)

WRITER_STYLES = {
    "Default": None,
    "Shakespeare": "lyrical drama",
    "Rumi": "spiritual simplicity",
}  # Simplified for brevity
STAR_OPTIONS = [1, 2, 3, 4, 5]


def stars_label(n):
    return "⭐" * n + "☆" * (5 - n)


tabs = st.tabs(["Write", "People", "Advanced"])

# ================= ADVANCED (MOVED UP OPTIONS) =================
with tabs[2]:
    st.subheader("Advanced settings")

    # ROW 1: Memory Toggles
    c1, c2, c3 = st.columns(3)
    st.session_state["adv_apply_prefs"] = c1.toggle(
        "Apply preferences", value=st.session_state["adv_apply_prefs"]
    )
    st.session_state["adv_use_people"] = c2.toggle(
        "Use people memory", value=st.session_state["adv_use_people"]
    )
    st.session_state["adv_show_injected_memory"] = c3.toggle(
        "Show memory", value=st.session_state["adv_show_injected_memory"]
    )

    # ROW 2: Rhyme, Cliché, and Debug (AS REQUESTED)
    c4, c5, c6 = st.columns(3)
    st.session_state["adv_rhyme"] = c4.checkbox(
        "Rhyme", value=st.session_state["adv_rhyme"]
    )
    st.session_state["adv_no_cliches"] = c5.checkbox(
        "No clichés mode", value=st.session_state["adv_no_cliches"]
    )
    st.session_state["adv_show_debug"] = c6.checkbox(
        "Show internal debug", value=st.session_state["adv_show_debug"]
    )

    st.divider()
    # REST OF ADVANCED OPTIONS
    st.session_state["adv_model"] = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o"])
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, float(st.session_state["adv_temperature"])
    )
    st.session_state["adv_must_include"] = st.text_input(
        "Must include", value=st.session_state["adv_must_include"]
    )
    st.session_state["adv_avoid"] = st.text_input(
        "Avoid", value=st.session_state["adv_avoid"]
    )

# ================= PEOPLE =================
with tabs[1]:
    st.subheader("People")
    with st.form("add_person"):
        name = st.text_input("Name")
        rel = st.text_input("Relationship")
        note = st.text_area("Note")
        if st.form_submit_button("Save person", type="primary"):  # SOLID RED
            storage.add_person(USER_ID, name, rel, note)
            st.rerun()

    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")  # LEGIBLE BOX

# ================= WRITE =================
with tabs[0]:
    st.subheader("Write")
    poem_name = st.text_input("Poem Name", value=st.session_state["poem_name"])
    theme = st.text_area("Theme", value="A meaningful moment.")

    c_style, c_lines = st.columns(2)
    style = c_style.selectbox("Format", ["free_verse", "haiku", "sonnet"])
    line_count = c_lines.slider("Length", 2, 60, 12)

    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Generate (fast)"):
        pass
    if c2.button("Generate + Improve", type="primary"):  # SOLID RED
        llm = create_llm(
            cfg,
            model=st.session_state["adv_model"],
            temperature=st.session_state["adv_temperature"],
        )
        out = generate_and_improve(
            llm,
            PoemRequest(theme=theme, style=style, line_count=int(line_count)),
            user_memory="",
        )
        if out.ok:
            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Version 2", "text": out.revised_poem},
            ]
            st.rerun()

    if not st.session_state["versions"]:
        st.info("No versions yet. Click Generate.")  # LEGIBLE BOX
    else:
        for i, v in enumerate(st.session_state["versions"]):
            st.markdown(f"### {v['label']}")
            st.code(v["text"])
            st.download_button(
                f"Download {v['label']}", v["text"], key=f"dl_{i}", type="primary"
            )  # SOLID RED

            with st.form(f"rate_{i}"):
                st.radio(
                    "Rating", STAR_OPTIONS, format_func=stars_label, horizontal=True
                )
                st.form_submit_button("Submit rating", type="primary")  # SOLID RED
