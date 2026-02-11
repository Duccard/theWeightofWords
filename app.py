import streamlit as st
from dotenv import load_dotenv

from core.config import load_config
from core.logging_setup import setup_logger
from core.llm_factory import create_llm
from core.orchestrator import generate_only, generate_and_improve, improve_again
from agent.schemas import PoemRequest

load_dotenv()
logger = setup_logger()

st.set_page_config(page_title="The Weight of Words", page_icon="📜", layout="wide")
st.title("📜 The Weight of Words")
st.caption("Simple input first. Advanced controls available in the Advanced tab.")

# ---- Config validation ----
try:
    cfg = load_config()
except Exception as e:
    st.error(str(e))
    st.stop()

# ---- Writer style presets ----
WRITER_STYLES = {
    "Default": None,
    "William Shakespeare": "elevated lyrical drama, balanced cadence, rich metaphor (no imitation or copying)",
    "Emily Dickinson": "compressed lines, sharp pauses, quiet intensity (no imitation or copying)",
    "Walt Whitman": "expansive free verse, long lines, generous human warmth (no imitation or copying)",
    "Pablo Neruda": "sensuous concrete imagery, emotional depth (no imitation or copying)",
    "T.S. Eliot": "modernist precision, surprising imagery (no imitation or copying)",
    "Langston Hughes": "musical cadence, plainspoken power (no imitation or copying)",
    "Rumi": "spiritual metaphor, luminous simplicity (no imitation or copying)",
    "Sylvia Plath": "intense imagery, emotional voltage (no imitation or copying)",
    "Seamus Heaney": "earthy tactile imagery, reflective lyricism (no imitation or copying)",
    "Matsuo Bashō": "minimalist stillness, nature clarity (no imitation or copying)",
    "Alexander Pushkin": "lyrical clarity, narrative elegance (no imitation or copying)",
    "Custom (type your own)": "CUSTOM",
}

# ---- Session state ----
for k in [
    "last_request",
    "last_poem",
    "last_critique",
    "last_revised",
    "versions",
    "poem_name",
]:
    st.session_state.setdefault(k, None)

if st.session_state["versions"] is None:
    st.session_state["versions"] = []

tabs = st.tabs(["Write", "Advanced"])

# ================= ADVANCED =================
with tabs[1]:
    st.subheader("Advanced settings")

    model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"], index=0)
    temperature = st.slider("Temperature", 0.0, 1.5, 0.9, 0.1)
    top_p = st.slider("Top-p", 0.1, 1.0, 0.95, 0.05)

    st.divider()
    must_include = st.text_input("Must include (comma-separated)")
    avoid = st.text_input("Avoid (comma-separated)")
    rhyme = st.checkbox("Rhyme", value=False)
    syllable_hints = st.text_input("Syllable hints (optional)")
    no_cliches = st.checkbox("No clichés mode", value=True)
    reading_level = st.selectbox(
        "Reading level", ["simple", "general", "advanced"], index=1
    )

    st.divider()
    audience = st.text_input("Audience (optional)")
    tone = st.selectbox(
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

llm = create_llm(cfg, model=model, temperature=temperature, top_p=top_p)

# ================= WRITE =================
with tabs[0]:
    st.subheader("Write")

    poem_name = st.text_input(
        "Poem Name", value=st.session_state["poem_name"] or "Untitled"
    )
    st.session_state["poem_name"] = poem_name

    theme_bg = st.text_area("Theme / Background", height=120)

    writer_choice = st.selectbox("Writer Style", list(WRITER_STYLES.keys()))
    custom_vibe = None
    if WRITER_STYLES[writer_choice] == "CUSTOM":
        custom_vibe = st.text_input("Custom writer vibe")

    occasion = st.selectbox(
        "Occasion (inspiration)",
        [
            "for inspiration",
            "apology",
            "birthday",
            "anniversary",
            "wedding",
            "graduation",
            "goodbye",
            "valentine",
        ],
    )

    style = st.selectbox(
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

    line_count = st.slider("Length (lines)", 2, 60, 12)
    acrostic_word = st.text_input("Acrostic word") if style == "acrostic" else None

    writer_vibe = (
        custom_vibe
        if WRITER_STYLES[writer_choice] == "CUSTOM"
        else WRITER_STYLES[writer_choice]
    )

    req = PoemRequest(
        occasion=occasion,
        theme=theme_bg or "a meaningful moment",
        audience=audience or None,
        style=style,
        tone=tone,
        writer_vibe=writer_vibe,
        must_include=[w.strip() for w in must_include.split(",") if w.strip()],
        avoid=[w.strip() for w in avoid.split(",") if w.strip()],
        line_count=line_count,
        rhyme=rhyme,
        syllable_hints=syllable_hints or None,
        no_cliches=no_cliches,
        reading_level=reading_level,
        acrostic_word=acrostic_word,
    )

    c1, c2, c3 = st.columns(3)
    btn_fast = c1.button("Generate only")
    btn_full = c2.button("Generate + Improve", type="primary")
    btn_again = c3.button("Improve again", disabled=not st.session_state["versions"])

    def stars(n):
        return "⭐" * n + "☆" * (5 - n)

    def render_versions():
        for i, v in enumerate(st.session_state["versions"], start=1):
            st.markdown(f"### {v['label']}")
            st.code(v["text"])
            st.download_button(
                f"Download {v['label']}",
                v["text"],
                file_name=f"{poem_name} - {v['label']}.txt",
                key=f"dl_{i}",
            )

    if btn_fast:
        out = generate_only(llm, req)
        st.session_state["versions"] = [{"label": "Version 1", "text": out.poem}]
        render_versions()

    if btn_full:
        out = generate_and_improve(llm, req)
        st.session_state["versions"] = [
            {"label": "Version 1", "text": out.poem},
            {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
        ]
        render_versions()

    if btn_again:
        base = st.session_state["versions"][-1]["text"]
        out = improve_again(llm, req, base)
        if out.revised_poem.strip() != base.strip():
            n = len(st.session_state["versions"]) + 1
            st.session_state["versions"].append(
                {"label": f"Version {n} (Upgraded)", "text": out.revised_poem}
            )
        render_versions()
