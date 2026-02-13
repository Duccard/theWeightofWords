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

# =========================================================
# Setup
# =========================================================
load_dotenv()
logger = setup_logger()

st.set_page_config(page_title="The Weight of Words", page_icon="📜", layout="wide")


def load_bg_image_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode()


BG_PATH = Path(__file__).parent / "assets" / "background.jpg"
bg_base64 = load_bg_image_base64(BG_PATH)

# =========================================================
# THEME / STYLE (DO NOT TOUCH)
# =========================================================
st.markdown(
    f"""
<link href="https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap" rel="stylesheet">

<style>
/* BACKGROUND */
.stApp {{
    background-image: url("data:image/jpeg;base64,{bg_base64}");
    background-size: cover;
    background-position: center;
    background-attachment: fixed;
}}

/* GLOBAL TEXT */
html, body, .stApp,
label, .stMarkdown, .stText,
.stCaption, .stSubheader, .stHeader,
p, span {{
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

.wow-subtitle {{
    text-align: center;
    font-size: 1.1rem;
    opacity: 0.9;
    color: #ffffff;
    margin-bottom: 2rem;
}}

/* INPUTS */
.stTextInput input,
.stTextArea textarea,
.stSelectbox div[role="combobox"] {{
    background: rgba(255,255,255,0.95) !important;
    color: #000000 !important;
    border-radius: 10px;
}}

/* OUTPUT */
pre, code {{
    background: rgba(0,0,0,0.35) !important;
    color: #ffffff !important;
    border-radius: 12px;
}}

/* GHOST BUTTONS */
.wow-ghost .stButton > button,
.wow-ghost form button {{
    background-color: transparent !important;
    color: #ffffff !important;
    border: 1.5px solid rgba(255,255,255,0.65) !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}}

.wow-ghost .stButton > button:hover,
.wow-ghost form button:hover {{
    background-color: transparent !important;
    color: #ffffff !important;
    border-color: rgba(255,255,255,0.65) !important;
}}
</style>

<div class="wow-title">The Weight of Words</div>
<div class="wow-subtitle">Beautiful poem generator</div>
""",
    unsafe_allow_html=True,
)

# =========================================================
# Config / Storage
# =========================================================
cfg = load_config()
storage = get_storage()
storage.init()

if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

# =========================================================
# Session defaults
# =========================================================
for k in ["versions", "rated_versions", "poem_name"]:
    st.session_state.setdefault(k, [] if k != "poem_name" else "Untitled")

# =========================================================
# Tabs
# =========================================================
tabs = st.tabs(["Write", "People", "Advanced"])

# =========================================================
# WRITE TAB
# =========================================================
with tabs[0]:
    st.subheader("Write")

    poem_name = st.text_input("Poem Name", st.session_state["poem_name"])
    st.session_state["poem_name"] = poem_name

    theme_bg = st.text_area("Theme / Background", height=120)

    style = st.selectbox(
        "Format",
        ["free_verse", "haiku", "limerick", "acrostic", "sonnet_like", "spoken_word"],
    )

    line_count = st.slider("Length (lines)", 2, 60, 12)

    req = PoemRequest(
        occasion="for inspiration",
        theme=theme_bg or "a meaningful moment",
        style=style,
        tone="warm",
        line_count=line_count,
    )

    llm = create_llm(cfg)

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown('<div class="wow-ghost">', unsafe_allow_html=True)
        btn_fast = st.button("Generate only (fast)")
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        btn_full = st.button("Generate + Improve", type="primary")

    with c3:
        st.markdown('<div class="wow-ghost">', unsafe_allow_html=True)
        btn_again = st.button(
            "Improve again", disabled=not st.session_state["versions"]
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with c4:
        st.markdown('<div class="wow-ghost">', unsafe_allow_html=True)
        btn_clear = st.button("Clear versions")
        st.markdown("</div>", unsafe_allow_html=True)

    if btn_clear:
        st.session_state["versions"] = []
        st.session_state["rated_versions"] = set()
        st.rerun()

    if btn_fast:
        out = generate_only(llm, req)
        st.session_state["versions"] = [{"label": "Version 1", "text": out.poem}]
        st.rerun()

    if btn_full:
        out = generate_and_improve(llm, req)
        st.session_state["versions"] = [
            {"label": "Version 1", "text": out.poem},
            {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
        ]
        st.rerun()

    if btn_again:
        base = st.session_state["versions"][-1]["text"]
        out = improve_again(llm, req, base)
        st.session_state["versions"].append(
            {
                "label": f"Version {len(st.session_state['versions'])+1}",
                "text": out.revised_poem,
            }
        )
        st.rerun()

    st.divider()
    st.subheader("Output")

    if not st.session_state["versions"]:
        st.info("No versions yet. Click Generate.")
    else:
        for i, v in enumerate(st.session_state["versions"]):
            st.markdown(f"### {v['label']}")
            st.code(v["text"])

            st.markdown('<div class="wow-ghost">', unsafe_allow_html=True)
            st.download_button(
                "Download TXT",
                v["text"],
                file_name=f"{poem_name}.txt",
                key=f"dl_{i}",
            )
            st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# PEOPLE TAB
# =========================================================
with tabs[1]:
    st.subheader("People")

    with st.form("add_person"):
        name = st.text_input("Name")
        rel = st.text_input("Relationship")
        note = st.text_area("Note")
        st.markdown('<div class="wow-ghost">', unsafe_allow_html=True)
        submitted = st.form_submit_button("Save person")
        st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        storage.add_person(USER_ID, name=name, relationship=rel, note=note)
        st.success("Saved.")

    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")

# =========================================================
# ADVANCED TAB
# =========================================================
with tabs[2]:
    st.subheader("Advanced")
    st.checkbox("Apply my preferences")
