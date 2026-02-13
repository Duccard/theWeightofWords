from __future__ import annotations

import uuid
import streamlit as st
from dotenv import load_dotenv
from pathlib import Path
import base64

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

    /* GLOBAL TEXT - Forcing white */
    html, body, .stApp, label, .stMarkdown, .stText,
    .stCaption, .stSubheader, .stHeader {{
        color: #ffffff !important;
    }}

    /* FIX BLUE ALERTS (st.info, etc) */
    div[data-testid="stNotification"] {{
        background-color: rgba(0, 0, 0, 0.6) !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
    }}
    div[data-testid="stNotification"] p {{
        color: #ffffff !important;
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
        background: rgba(0,0,0,0.35) !important;
        color: #ffffff !important;
        border-radius: 12px;
    }}

    /* BUTTONS - Base Styles */
    .stButton > button, .stDownloadButton > button {{
        background-color: rgba(255,255,255,0.18) !important;
        color: #ffffff !important;
        border-radius: 10px;
    }}

    /* PRIMARY BUTTONS (Reddish - Match Switches) */
    .stButton > button[data-testid="baseButton-primary"],
    .stDownloadButton > button[data-testid="baseButton-primary"],
    .stForm [data-testid="stFormSubmitButton"] > button {{
        background-color: #FF4B4B !important;
        color: #ffffff !important;
        border: none !important;
    }}
    </style>

    <div class="wow-title">The Weight of Words</div>
    <div class="wow-subtitle" style="text-align: center; color: white; opacity: 0.9; margin-bottom: 2rem;">Beautiful poem generator</div>
    """,
    unsafe_allow_html=True,
)

# ... (Config, Storage, User_ID, Styles remain same)
try:
    cfg = load_config()
    storage = get_storage()
    storage.init()
except Exception as e:
    st.error(str(e))
    st.stop()

if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

WRITER_STYLES = {
    "Default": None,
    "William Shakespeare": "elevated lyrical drama, balanced cadence, rich metaphor",
    "Emily Dickinson": "compressed lines, sharp pauses, quiet intensity",
    "Walt Whitman": "expansive free verse, long lines, generous human warmth",
    "Pablo Neruda": "sensuous concrete imagery, emotional depth",
    "T.S. Eliot": "modernist precision, surprising imagery",
    "Langston Hughes": "musical cadence, plainspoken power",
    "Rumi": "spiritual metaphor, luminous simplicity",
    "Sylvia Plath": "intense imagery, emotional voltage",
    "Seamus Heaney": "earthy tactile imagery, reflective lyricism",
    "Matsuo Bashō": "minimalist stillness, nature clarity",
    "Alexander Pushkin": "lyrical clarity, narrative elegance",
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

# Defaults
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


def build_user_memory(storage_obj, user_id, include_prefs, include_people):
    parts = []
    if include_prefs:
        taste = storage_obj.get_taste_profile(user_id) or {}
        if int(taste.get("total_ratings", 0) or 0) > 0:
            parts.append(f"User preferences: {taste.get('prefer_rhyme_score')}")
    if include_people:
        ppl = storage_obj.list_people(user_id) or []
        if ppl:
            parts.append("People: " + ", ".join([p["name"] for p in ppl]))
    return "\n\n".join(parts)


main_tabs = st.tabs(["Write", "People", "Advanced"])

# ================= ADVANCED (REORDERED) =================
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

    st.session_state["adv_show_debug"] = st.checkbox(
        "Show internal debug", value=st.session_state["adv_show_debug"]
    )  # MOVED UP

    st.divider()
    st.markdown("### Model & Constraints")
    st.session_state["adv_model"] = st.selectbox(
        "Model", ["gpt-4o-mini", "gpt-4o"], index=0
    )
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, float(st.session_state["adv_temperature"])
    )

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

# ================= PEOPLE =================
with main_tabs[1]:
    st.subheader("People")
    with st.form("add_person_form", clear_on_submit=True):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship")
        note = st.text_area("Note (optional)", height=80)
        submitted = st.form_submit_button("Save person", type="primary")  # REDDISH

    st.divider()
    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")  # NOW DARK/WHITE
    else:
        for p in people:
            st.markdown(f"👤 **{p['name']}** — *{p['relationship']}*")

# ================= WRITE =================
with main_tabs[0]:
    st.subheader("Write")
    user_memory = build_user_memory(
        storage,
        USER_ID,
        st.session_state["adv_apply_prefs"],
        st.session_state["adv_use_people"],
    )

    poem_name = st.text_input("Poem Name", value=st.session_state["poem_name"])
    theme_bg = st.text_area(
        "Theme / Background", height=120, value="Write a sincere poem."
    )
    writer_style_choice = st.selectbox("Writer Style", list(WRITER_STYLES.keys()))

    c_style, c_lines = st.columns(2)
    style = c_style.selectbox("Format", ["free_verse", "haiku", "sonnet_like"])
    line_count = c_lines.slider("Length", 2, 60, 12)

    llm = create_llm(
        cfg,
        model=st.session_state["adv_model"],
        temperature=st.session_state["adv_temperature"],
    )

    c1, c2, c3, c4 = st.columns(4)
    btn_fast = c1.button("Generate (fast)")
    btn_full = c2.button("Generate + Improve", type="primary")  # REDDISH
    btn_again = c3.button(
        "Improve again", disabled=len(st.session_state["versions"]) == 0
    )
    btn_clear = c4.button("Clear")

    if btn_full:
        out = generate_and_improve(
            llm,
            PoemRequest(theme=theme_bg, style=style, line_count=int(line_count)),
            user_memory,
        )
        if out.ok:
            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Version 2", "text": out.revised_poem},
            ]
            st.rerun()

    st.divider()
    if not st.session_state["versions"]:
        st.info("No versions yet. Click Generate.")  # NOW DARK/WHITE
    else:
        for i, v in enumerate(st.session_state["versions"]):
            st.markdown(f"### {v['label']}")
            st.code(v["text"])
            st.download_button(
                f"Download {v['label']}",
                v["text"],
                file_name=f"poem.txt",
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
                    ):  # REDDISH
                        st.session_state["rated_versions"].add(v["label"])
                        st.rerun()
