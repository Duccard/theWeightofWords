from __future__ import annotations

import uuid
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path
import base64

# --- CUSTOM IMPORTS (Ensure these exist in your project) ---
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

    /* LEGIBILITY FIX FOR INFO/BLUE BOXES */
    div[data-testid="stNotification"] {{
        background-color: rgba(0, 0, 0, 0.7) !important;
        border: 1px solid #FF4B4B !important;
        border-radius: 10px;
    }}
    div[data-testid="stNotification"] p {{
        color: #ffffff !important;
        font-weight: 500;
    }}

    /* TABS */
    button[data-baseweb="tab"] {{
        color: #ffffff !important;
        font-weight: 600;
    }}

    /* TITLE */
    .wow-title {{
        font-family: 'Great Vibes', cursive;
        font-size: 72px;
        text-align: center;
        color: #ffffff;
        margin-bottom: 0.2rem;
    }}

    /* INPUTS */
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox div[role="combobox"] {{
        background: rgba(255,255,255,0.95) !important;
        color: #000000 !important;
        border-radius: 10px;
    }}

    /* POEM OUTPUT */
    pre, code {{
        background: rgba(0,0,0,0.4) !important;
        color: #ffffff !important;
        border-radius: 12px;
    }}

    /* BASE BUTTON STYLE (Secondary/Outline) */
    .stButton > button, .stDownloadButton > button {{
        background-color: rgba(255,255,255,0.1) !important;
        color: #ffffff !important;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.3) !important;
    }}

    /* SOLID PRIMARY BUTTONS (Reddish - Matches Switches) */
    /* This targets Generate+Improve, Save Person, Submit Rating, and Downloads */
    .stButton > button[data-testid="baseButton-primary"],
    .stDownloadButton > button[data-testid="baseButton-primary"],
    div[data-testid="stForm"] button[data-testid="baseButton-primary"] {{
        background-color: #FF4B4B !important;
        color: white !important;
        border: none !important;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.2);
    }}

    /* Hover effect for primary buttons */
    .stButton > button[data-testid="baseButton-primary"]:hover {{
        background-color: #FF3333 !important;
        border: none !important;
    }}
    </style>

    <div class="wow-title">The Weight of Words</div>
    <div class="wow-subtitle" style="text-align: center; color: white; opacity: 0.9; margin-bottom: 2rem;">Beautiful poem generator</div>
    """,
    unsafe_allow_html=True,
)

# --- LOGIC & STATE ---
try:
    cfg = load_config()
    storage = get_storage()
    storage.init()
except Exception as e:
    st.error(f"Initialization error: {e}")
    st.stop()

if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

WRITER_STYLES = {
    "Default": None,
    "William Shakespeare": "elevated lyrical drama",
    "Emily Dickinson": "quiet intensity",
    "Walt Whitman": "generous human warmth",
    "Pablo Neruda": "sensuous concrete imagery",
    "T.S. Eliot": "modernist precision",
    "Langston Hughes": "musical cadence",
    "Rumi": "spiritual metaphor",
    "Sylvia Plath": "intense imagery",
    "Seamus Heaney": "earthy tactile imagery",
    "Matsuo Bashō": "minimalist stillness",
    "Alexander Pushkin": "lyrical clarity",
}

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
if st.session_state["versions"] is None:
    st.session_state["versions"] = []
if st.session_state["rated_versions"] is None:
    st.session_state["rated_versions"] = set()

# RESTORED FULL ADVANCED DEFAULTS
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
}
for key, val in defaults.items():
    st.session_state.setdefault(key, val)

STAR_OPTIONS = [1, 2, 3, 4, 5]


def stars_label(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


# --- APP LAYOUT ---
main_tabs = st.tabs(["Write", "People", "Advanced"])

# ================= ADVANCED =================
with main_tabs[2]:
    st.subheader("Advanced settings")
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

    # INTERNAL DEBUG MOVED UP AS REQUESTED
    st.session_state["adv_show_debug"] = st.checkbox(
        "Show internal debug", value=st.session_state["adv_show_debug"]
    )

    st.divider()
    st.markdown("### Model & Personalization")
    st.session_state["adv_model"] = st.selectbox(
        "Model", ["gpt-4o-mini", "gpt-4o"], index=0
    )
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, float(st.session_state["adv_temperature"])
    )
    st.session_state["adv_top_p"] = st.slider(
        "Top-p", 0.1, 1.0, float(st.session_state["adv_top_p"])
    )

    st.divider()
    st.markdown("### Constraints")
    st.session_state["adv_must_include"] = st.text_input(
        "Must include", value=st.session_state["adv_must_include"]
    )
    st.session_state["adv_avoid"] = st.text_input(
        "Avoid", value=st.session_state["adv_avoid"]
    )
    st.session_state["adv_reading_level"] = st.selectbox(
        "Reading level", ["simple", "general", "advanced"], index=1
    )
    st.session_state["adv_tone"] = st.selectbox(
        "Tone",
        ["warm", "funny", "romantic", "somber", "hopeful", "minimalist"],
        index=0,
    )
    st.session_state["adv_rhyme"] = st.checkbox(
        "Rhyme", value=st.session_state["adv_rhyme"]
    )
    st.session_state["adv_no_cliches"] = st.checkbox(
        "No clichés mode", value=st.session_state["adv_no_cliches"]
    )

# ================= PEOPLE =================
with main_tabs[1]:
    st.subheader("People")
    with st.form("add_person_form", clear_on_submit=True):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship")
        note = st.text_area("Note (optional)", height=80)
        submitted = st.form_submit_button("Save person", type="primary")  # SOLID RED

    st.divider()
    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")  # LEGIBLE BOX
    else:
        for p in people:
            st.markdown(f"👤 **{p['name']}** — *{p['relationship']}*")

# ================= WRITE =================
with main_tabs[0]:
    st.subheader("Write")

    poem_name = st.text_input("Poem Name", value=st.session_state["poem_name"])
    theme_bg = st.text_area(
        "Theme / Background", height=120, value="Write a sincere poem."
    )
    writer_style_choice = st.selectbox("Writer Style", list(WRITER_STYLES.keys()))

    c_style, c_lines = st.columns(2)
    style = c_style.selectbox(
        "Format", ["free_verse", "haiku", "sonnet_like", "limerick", "acrostic"]
    )
    line_count = c_lines.slider("Length", 2, 60, 12)

    llm = create_llm(
        cfg,
        model=st.session_state["adv_model"],
        temperature=st.session_state["adv_temperature"],
    )

    c1, c2, c3, c4 = st.columns(4)
    btn_fast = c1.button("Generate (fast)")
    btn_full = c2.button("Generate + Improve", type="primary")  # SOLID RED
    btn_again = c3.button(
        "Improve again", disabled=len(st.session_state["versions"]) == 0
    )
    btn_clear = c4.button("Clear")

    if btn_full:
        req = PoemRequest(
            theme=theme_bg,
            style=style,
            line_count=int(line_count),
            writer_vibe=WRITER_STYLES[writer_style_choice],
            tone=st.session_state["adv_tone"],
            rhyme=st.session_state["adv_rhyme"],
        )
        out = generate_and_improve(
            llm, req, user_memory=""
        )  # Replace empty string with your build_user_memory call
        if out.ok:
            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
            ]
            st.rerun()

    st.divider()
    if not st.session_state["versions"]:
        st.info("No versions yet. Click Generate.")  # LEGIBLE BOX
    else:
        for i, v in enumerate(st.session_state["versions"]):
            st.markdown(f"### {v['label']}")
            st.code(v["text"])
            st.download_button(
                f"Download {v['label']}",
                v["text"],
                file_name=f"{poem_name}.txt",
                key=f"dl_{i}",
                type="primary",
            )

            if v["label"] not in st.session_state["rated_versions"]:
                with st.form(key=f"rate_{i}"):
                    r = st.radio(
                        "Rating", STAR_OPTIONS, format_func=stars_label, horizontal=True
                    )
                    if st.form_submit_button(
                        "Submit rating", type="primary"
                    ):  # SOLID RED
                        st.session_state["rated_versions"].add(v["label"])
                        st.rerun()
