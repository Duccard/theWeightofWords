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


# --- UTILS ---
def load_bg_image_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


# --- PAGE CONFIG ---
st.set_page_config(page_title="The Weight of Words", page_icon="📜", layout="centered")

# --- LOAD ASSETS ---
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

    /* GLOBAL TEXT - Forcing white */
    html, body, .stApp, label, .stMarkdown, .stText,
    .stCaption, .stSubheader, .stHeader, p {{
        color: #ffffff !important;
    }}

    /* FIX NOTIFICATIONS */
    div[data-testid="stNotification"] {{
        background-color: rgba(0, 0, 0, 0.7) !important;
        border: 1px solid #FF4B4B !important;
        border-radius: 10px;
    }}

    /* TABS */
    button[data-baseweb="tab"] {{
        color: #ffffff !important;
        font-weight: 600;
    }}

    /* TITLE STYLE */
    .wow-title {{
        font-family: 'Great Vibes', cursive;
        font-size: 80px;
        text-align: center;
        color: #ffffff;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        margin-bottom: 0.1rem;
    }}

    /* INPUT BOXES */
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox div[role="combobox"] {{
        background: rgba(255,255,255,0.95) !important;
        color: #000000 !important;
        border-radius: 10px;
    }}

    /* CODE BLOCKS (POEM OUTPUT) */
    pre, code {{
        background: rgba(0,0,0,0.5) !important;
        color: #ffffff !important;
        border-radius: 12px;
    }}

    /* BUTTONS - Secondary (Transparent-ish) */
    .stButton > button, .stDownloadButton > button {{
        background-color: rgba(255,255,255,0.15) !important;
        color: #ffffff !important;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.2) !important;
    }}

    /* PRIMARY BUTTONS - SOLID RED (Generate, Save, Submit) */
    button[kind="primary"] {{
        background-color: #FF4B4B !important;
        color: #ffffff !important;
        border: none !important;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.3) !important;
    }}
    
    button[kind="primary"]:hover {{
        background-color: #FF3333 !important;
        border: none !important;
    }}
    </style>

    <div class="wow-title">The Weight of Words</div>
    <div style="text-align: center; color: white; opacity: 0.8; margin-bottom: 2rem; font-style: italic;">Beautiful poem generator</div>
    """,
    unsafe_allow_html=True,
)

# --- CORE INITIALIZATION ---
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

# --- PRESETS ---
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

# --- STATE MANAGEMENT ---
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

# Advanced defaults
defaults = {
    "adv_model": "gpt-4o-mini",
    "adv_temperature": 0.9,
    "adv_top_p": 0.95,
    "adv_apply_prefs": True,
    "adv_use_people": True,
    "adv_show_injected_memory": False,
    "adv_rhyme": False,
    "adv_no_cliches": True,
    "adv_reading_level": "general",
    "adv_tone": "warm",
    "adv_show_debug": False,
    "adv_must_include": "",
    "adv_avoid": "",
}
for key, val in defaults.items():
    st.session_state.setdefault(key, val)


def stars_label(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


STAR_OPTIONS = [1, 2, 3, 4, 5]


# --- REUSABLE LOGIC ---
def build_user_memory(storage_obj, user_id, include_prefs, include_people):
    parts = []
    if include_prefs:
        taste = storage_obj.get_taste_profile(user_id) or {}
        if int(taste.get("total_ratings", 0) or 0) > 0:
            parts.append(f"Learned Taste: {taste}")
    if include_people:
        ppl = storage_obj.list_people(user_id) or []
        if ppl:
            parts.append(
                "Known People: "
                + ", ".join([f"{p['name']} ({p['relationship']})" for p in ppl])
            )
    return "\n\n".join(parts)


main_tabs = st.tabs(["Write", "People", "Advanced"])

# ================= ADVANCED =================
with main_tabs[2]:
    st.subheader("Advanced settings")
    c1, c2, c3 = st.columns(3)
    st.session_state["adv_apply_prefs"] = c1.toggle(
        "Apply Preferences", value=st.session_state["adv_apply_prefs"]
    )
    st.session_state["adv_use_people"] = c2.toggle(
        "Use People Memory", value=st.session_state["adv_use_people"]
    )
    st.session_state["adv_show_injected_memory"] = c3.toggle(
        "Show Memory", value=st.session_state["adv_show_injected_memory"]
    )

    c4, c5, c6 = st.columns(3)
    st.session_state["adv_rhyme"] = c4.checkbox(
        "Rhyme", value=st.session_state["adv_rhyme"]
    )
    st.session_state["adv_no_cliches"] = c5.checkbox(
        "No Clichés", value=st.session_state["adv_no_cliches"]
    )
    st.session_state["adv_show_debug"] = c6.checkbox(
        "Internal Debug", value=st.session_state["adv_show_debug"]
    )

    st.divider()
    st.session_state["adv_model"] = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o"])
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, float(st.session_state["adv_temperature"])
    )

    st.divider()
    if st.checkbox("See taste profile"):
        st.json(storage.get_taste_profile(USER_ID))

# ================= PEOPLE =================
with main_tabs[1]:
    st.subheader("People")
    with st.form("add_person_form", clear_on_submit=True):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship")
        note = st.text_area("Note (optional)")
        if st.form_submit_button("Save Person", type="primary"):
            if name and relationship:
                storage.add_person(
                    USER_ID, name=name, relationship=relationship, note=note
                )
                st.success(f"Saved {name}")
                st.rerun()  # Forces instant refresh

    st.divider()
    saved_ppl = storage.list_people(USER_ID)
    if not saved_ppl:
        st.info("No people saved yet.")
    else:
        for p in saved_ppl:
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
    if st.session_state["adv_show_injected_memory"]:
        st.code(user_memory)

    poem_name = st.text_input(
        "Poem Name", value=st.session_state["poem_name"] or "Untitled"
    )
    theme_bg = st.text_area("Theme / Background", value="Write a sincere poem.")

    c_style, c_lines = st.columns(2)
    style = c_style.selectbox(
        "Format", ["free_verse", "haiku", "sonnet_like", "limerick"]
    )
    line_count = c_lines.slider("Length", 2, 60, 12)

    writer_style_choice = st.selectbox("Writer Style", list(WRITER_STYLES.keys()))

    c1, c2, c3, c4 = st.columns(4)
    btn_fast = c1.button("Fast Gen")
    btn_full = c2.button("Generate + Improve", type="primary")
    btn_again = c3.button(
        "Improve again", disabled=len(st.session_state["versions"]) == 0
    )
    btn_clear = c4.button("Clear")

    if btn_full:
        llm = create_llm(
            cfg,
            model=st.session_state["adv_model"],
            temperature=st.session_state["adv_temperature"],
        )
        req = PoemRequest(
            theme=theme_bg,
            style=style,
            line_count=int(line_count),
            writer_vibe=WRITER_STYLES[writer_style_choice],
            rhyme=st.session_state["adv_rhyme"],
            tone=st.session_state["adv_tone"],
        )
        out = generate_and_improve(llm, req, user_memory)
        if out.ok:
            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
            ]
            st.rerun()

    if btn_clear:
        st.session_state["versions"] = []
        st.rerun()

    st.divider()
    if st.session_state["versions"]:
        for i, v in enumerate(st.session_state["versions"]):
            st.markdown(f"### {v['label']}")
            st.code(v["text"])
            st.download_button(
                f"Download {v['label']}", v["text"], key=f"dl_{i}", type="primary"
            )

            # Simple Rating inline
            if v["label"] not in st.session_state["rated_versions"]:
                with st.expander(f"Rate {v['label']}"):
                    with st.form(f"f_rate_{i}"):
                        star = st.radio(
                            "Rating",
                            STAR_OPTIONS,
                            format_func=stars_label,
                            horizontal=True,
                        )
                        if st.form_submit_button("Submit", type="primary"):
                            st.session_state["rated_versions"].add(v["label"])
                            st.success("Rated!")
                            st.rerun()
