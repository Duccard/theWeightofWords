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

    /* GLOBAL TEXT - Forcing white on all possible Streamlit text elements */
    html, body, .stApp, label, .stMarkdown, .stText,
    .stCaption, .stSubheader, .stHeader, 
    div[data-testid="stNotification"] p, 
    div[data-testid="stNotification"] {{
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

    /* PRIMARY BUTTONS (Orange Style) */
    .stButton > button[data-testid="baseButton-primary"],
    .stDownloadButton > button[data-testid="baseButton-primary"],
    .stForm [data-testid="stFormSubmitButton"] > button {{
        background-color: #FF8C00 !important;
        color: #ffffff !important;
        border: none !important;
    }}
    </style>

    <div class="wow-title">The Weight of Words</div>
    <div class="wow-subtitle">Beautiful poem generator</div>
    """,
    unsafe_allow_html=True,
)

# ---- Config validation ----
try:
    cfg = load_config()
except Exception as e:
    st.error(str(e))
    st.stop()

storage = get_storage()
try:
    storage.init()
except Exception as e:
    st.error(f"Storage init failed: {e}")
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

# Restored Session State logic
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

# Restore ALL Advanced defaults
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


def stars_label(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


def build_user_memory(
    storage_obj, user_id: str, include_prefs: bool, include_people: bool
) -> str:
    parts = []
    if include_prefs:
        taste = storage_obj.get_taste_profile(user_id) or {}
        if int(taste.get("total_ratings", 0) or 0) > 0:
            rhyme_score = float(taste.get("prefer_rhyme_score", 0.0))
            rhyme_hint = (
                "prefers rhyme"
                if rhyme_score > 1
                else "prefers no rhyme" if rhyme_score < -1 else "neutral"
            )
            parts.append(
                f"Preferences: {rhyme_hint}, ~{taste.get('avg_line_count')} lines."
            )
    if include_people:
        ppl = storage_obj.list_people(user_id) or []
        if ppl:
            lines = [
                f"- {p['name']} ({p['relationship']}): {p.get('note','')}"
                for p in ppl[:10]
            ]
            parts.append("People memory:\n" + "\n".join(lines))
    return "\n\n".join(parts).strip() or "None"


def person_icon(rel: str) -> str:
    rel = (rel or "").lower()
    if any(x in rel for x in ["girl", "boy", "partner"]):
        return "❤️"
    if "friend" in rel:
        return "🧑‍🤝‍🧑"
    return "👤"


main_tabs = st.tabs(["Write", "People", "Advanced"])

# ================= FULL RESTORED ADVANCED =================
with main_tabs[2]:
    st.subheader("Advanced settings")
    st.caption(f"Storage backend: **{storage.backend_name()}**")
    st.markdown("### Personalization & constraints")
    c1, c2, c3 = st.columns([1, 1, 1])
    st.session_state["adv_apply_prefs"] = c1.toggle(
        "Apply my preferences", value=st.session_state["adv_apply_prefs"]
    )
    st.session_state["adv_use_people"] = c2.toggle(
        "Use people memory", value=st.session_state["adv_use_people"]
    )
    st.session_state["adv_show_injected_memory"] = c3.toggle(
        "Show injected memory", value=st.session_state["adv_show_injected_memory"]
    )

    c4, c5, c6 = st.columns([1, 1, 1])
    st.session_state["adv_rhyme"] = c4.checkbox(
        "Rhyme", value=st.session_state["adv_rhyme"]
    )
    st.session_state["adv_no_cliches"] = c5.checkbox(
        "No clichés mode", value=st.session_state["adv_no_cliches"]
    )
    st.session_state["adv_reading_level"] = c6.selectbox(
        "Reading level", ["simple", "general", "advanced"], index=1
    )

    st.session_state["adv_audience"] = st.text_input(
        "Audience (optional)", value=st.session_state["adv_audience"]
    )

    st.divider()
    st.markdown("### Model")
    st.session_state["adv_model"] = st.selectbox(
        "Model", ["gpt-4o-mini", "gpt-4o"], index=0
    )
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, float(st.session_state["adv_temperature"]), 0.1
    )
    st.session_state["adv_top_p"] = st.slider(
        "Top-p", 0.1, 1.0, float(st.session_state["adv_top_p"]), 0.05
    )

    st.divider()
    st.markdown("### Extra constraints")
    st.session_state["adv_must_include"] = st.text_input(
        "Must include (comma-separated)", value=st.session_state["adv_must_include"]
    )
    st.session_state["adv_avoid"] = st.text_input(
        "Avoid (comma-separated)", value=st.session_state["adv_avoid"]
    )
    st.session_state["adv_syllable_hints"] = st.text_input(
        "Syllable hints", value=st.session_state["adv_syllable_hints"]
    )
    st.session_state["adv_tone"] = st.selectbox(
        "Tone",
        [
            "warm",
            "funny",
            "romantic",
            "somber",
            "hopeful",
            "angry",
            "motivational",
            "surreal",
            "minimalist",
        ],
        index=0,
    )
    st.session_state["adv_show_debug"] = st.checkbox(
        "Show internal debug", value=st.session_state["adv_show_debug"]
    )

# LLM creation
llm = create_llm(
    cfg,
    model=st.session_state["adv_model"],
    temperature=st.session_state["adv_temperature"],
    top_p=st.session_state["adv_top_p"],
)

# ================= PEOPLE =================
with main_tabs[1]:
    st.subheader("People")
    with st.form("add_person_form", clear_on_submit=True):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship")
        note = st.text_area("Note (optional)", height=80)
        submitted = st.form_submit_button("Save person", type="primary")

    if submitted:
        storage.add_person(USER_ID, name=name, relationship=relationship, note=note)
        st.success("Saved.")
        st.rerun()

    st.divider()
    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")
    else:
        for p in people:
            st.markdown(
                f"{person_icon(p.get('relationship'))} **{p['name']}** — *{p['relationship']}*"
            )
            if p.get("note"):
                st.caption(p["note"])

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
        "Poem Name", value=(st.session_state["poem_name"] or "Untitled")
    )
    st.session_state["poem_name"] = poem_name

    theme_bg = st.text_area(
        "Theme / Background", height=120, value="Write a sincere poem."
    )
    writer_style_choice = st.selectbox(
        "Writer Style", list(WRITER_STYLES.keys()), index=0
    )

    c_style, c_lines = st.columns(2)
    style = c_style.selectbox(
        "Format",
        [
            "free_verse",
            "haiku",
            "limerick",
            "acrostic",
            "sonnet_like",
            "spoken_word",
            "rhymed_couplets",
        ],
    )
    line_count = c_lines.slider("Length (lines)", 2, 60, 12)

    req = PoemRequest(
        occasion="inspiration",
        theme=theme_bg,
        style=style,
        line_count=int(line_count),
        writer_vibe=WRITER_STYLES[writer_style_choice],
        rhyme=bool(st.session_state["adv_rhyme"]),
        tone=st.session_state["adv_tone"],
        audience=st.session_state["adv_audience"],
        no_cliches=st.session_state["adv_no_cliches"],
        reading_level=st.session_state["adv_reading_level"],
    )

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    btn_fast = c1.button("Generate only (fast)")
    btn_full = c2.button("Generate + Improve", type="primary")  # NOW ORANGE
    btn_again = c3.button(
        "Improve again", disabled=len(st.session_state["versions"]) == 0
    )
    btn_clear = c4.button("Clear versions")

    if btn_clear:
        st.session_state["versions"] = []
        st.rerun()

    if btn_fast:
        out = generate_only(llm, req, user_memory)
        if out.ok:
            st.session_state["versions"] = [{"label": "Version 1", "text": out.poem}]
            st.session_state["last_request"] = req
            st.rerun()

    if btn_full:
        out = generate_and_improve(llm, req, user_memory)
        if out.ok:
            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
            ]
            st.session_state["last_request"] = req
            st.rerun()

    if btn_again:
        out = improve_again(
            llm,
            st.session_state["last_request"],
            st.session_state["versions"][-1]["text"],
            user_memory,
        )
        if out.ok:
            st.session_state["versions"].append(
                {
                    "label": f"Version {len(st.session_state['versions'])+1} (Upgraded)",
                    "text": out.revised_poem,
                }
            )
            st.rerun()

    st.divider()
    if not st.session_state["versions"]:
        st.info("No versions yet. Click Generate.")
    else:
        for i, v in enumerate(st.session_state["versions"]):
            st.markdown(f"### {v['label']}")
            st.code(v["text"])
            st.download_button(
                f"Download {v['label']}",
                v["text"],
                file_name=f"{poem_name}_{v['label']}.txt",
                key=f"dl_{i}",
                type="primary",
            )

            if v["label"] not in st.session_state["rated_versions"]:
                with st.form(key=f"rate_{i}"):
                    r = st.radio(
                        "Rating", STAR_OPTIONS, format_func=stars_label, horizontal=True
                    )
                    if st.form_submit_button("Submit rating", type="primary"):
                        storage.add_rating(
                            USER_ID,
                            poem_name,
                            v["label"],
                            req.model_dump(),
                            v["text"],
                            r,
                        )
                        st.session_state["rated_versions"].add(v["label"])
                        st.rerun()
