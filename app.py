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

# ---- Writer style presets (Default + 11) ----
WRITER_STYLES = {
    "Default": None,
    "William Shakespeare": "elevated lyrical drama, balanced cadence, rich metaphor (no imitation or copying)",
    "Emily Dickinson": "compressed lines, sharp pauses, quiet intensity, slantwise insight (no imitation or copying)",
    "Walt Whitman": "expansive free verse, long lines, direct address, generous human warmth (no imitation or copying)",
    "Pablo Neruda": "sensuous concrete imagery, emotional depth, lush metaphors (no imitation or copying)",
    "T.S. Eliot": "modernist precision, surprising images, controlled fragmentation (no imitation or copying)",
    "Langston Hughes": "voice-forward rhythm, musical cadence, plainspoken power (no imitation or copying)",
    "Rumi": "spiritual metaphor, parable-like turns, luminous simplicity (no imitation or copying)",
    "Sylvia Plath": "intense precision, striking metaphors, emotional voltage (no imitation or copying)",
    "Seamus Heaney": "grounded tactile imagery, earthy detail, reflective lyricism (no imitation or copying)",
    "Matsuo Bashō": "minimalist stillness, nature clarity, moment-awareness (no imitation or copying)",
    "Alexander Pushkin": "lyrical clarity, narrative elegance, emotional restraint (no imitation or copying)",
    "Custom (type your own)": "CUSTOM",
}

# ---- Session state ----
for k in ["last_request", "last_poem", "last_critique", "last_revised"]:
    st.session_state.setdefault(k, None)

tabs = st.tabs(["Write", "Advanced"])

# -------------------- Advanced settings --------------------
with tabs[1]:
    st.subheader("Advanced settings")

    st.markdown("### Model")
    model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"], index=0)
    temperature = st.slider("Temperature", 0.0, 1.5, 0.9, 0.1)
    top_p = st.slider("Top-p", 0.1, 1.0, 0.95, 0.05)

    st.divider()
    st.markdown("### Constraints")
    must_include = st.text_input("Must include (comma-separated)", value="")
    avoid = st.text_input("Avoid (comma-separated)", value="")

    rhyme = st.checkbox("Rhyme", value=False)
    syllable_hints = st.text_input("Syllable hints (optional)", value="")
    no_cliches = st.checkbox("No clichés mode", value=True)
    reading_level = st.selectbox(
        "Reading level", ["simple", "general", "advanced"], index=1
    )

    st.divider()
    st.markdown("### Optional extra context")
    audience = st.text_input("Audience (optional)", value="")
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
    show_debug = st.checkbox("Show internal debug (draft & critique)", value=False)

# Create LLM after advanced settings exist
llm = create_llm(cfg, model=model, temperature=temperature, top_p=top_p)

# -------------------- Write tab (simple) --------------------
with tabs[0]:
    st.subheader("Write")

    theme_bg = st.text_area(
        "Theme / Background",
        value="Write a sincere apology poem. Make it specific and human.",
        height=120,
        help="A single description of what you want. This is the main input.",
    )

    writer_style_choice = st.selectbox(
        "Writer Style",
        list(WRITER_STYLES.keys()),
        index=0,
        help="Choose a vibe. We evoke mood/techniques only—no imitation or copying.",
    )

    custom_writer_vibe = None
    if WRITER_STYLES.get(writer_style_choice) == "CUSTOM":
        custom_writer_vibe = st.text_input(
            "Custom writer vibe",
            value="classical storyteller energy (no copying)",
            help="Describe the style vibe in your own words.",
        )

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
        index=0,
        help="Used as inspiration framing, not a strict requirement.",
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
        index=0,
    )

    line_count = st.slider("Length (lines)", 2, 60, 12)

    acrostic_word = None
    if style == "acrostic":
        acrostic_word = st.text_input("Acrostic word", value="WINTER")

    # Build writer vibe based on selection
    if WRITER_STYLES.get(writer_style_choice) == "CUSTOM":
        writer_vibe = (custom_writer_vibe or "").strip() or None
    else:
        writer_vibe = WRITER_STYLES.get(writer_style_choice)

    # Convert advanced values
    must_list = [w.strip() for w in must_include.split(",") if w.strip()]
    avoid_list = [w.strip() for w in avoid.split(",") if w.strip()]
    syllable_val = syllable_hints.strip() or None
    audience_val = audience.strip() or None

    # Build request
    req = PoemRequest(
        occasion=occasion,
        theme=theme_bg.strip() or "a meaningful moment",
        audience=audience_val,
        style=style,
        tone=tone,  # tone moved to Advanced
        writer_vibe=writer_vibe,
        must_include=must_list,
        avoid=avoid_list,
        line_count=line_count,
        rhyme=rhyme,
        syllable_hints=syllable_val,
        no_cliches=no_cliches,
        reading_level=reading_level,
        acrostic_word=(acrostic_word.strip() if acrostic_word else None),
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        btn_fast = st.button("Generate only (fast)")
    with c2:
        btn_full = st.button("Generate + Improve", type="primary")
    with c3:
        btn_again = st.button(
            "Improve again", disabled=st.session_state["last_poem"] is None
        )

    st.divider()
    st.subheader("Output")

    # ---- Actions ----
    if btn_fast:
        out = generate_only(llm, req)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = None
            st.session_state["last_revised"] = None

            # Simple output: show poem only
            st.code(out.poem)

            # Optional debug
            if show_debug:
                st.markdown("#### Debug: draft")
                st.code(out.poem)

    if btn_full:
        out = generate_and_improve(llm, req)
        if not out.ok:
            st.error(out.error_user)
        else:
            # Store internals in session but hide by default
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = out.critique
            st.session_state["last_revised"] = out.revised_poem

            # Simple output: show revised only
            st.code(out.revised_poem)

            st.download_button(
                "Download (.txt)", out.revised_poem, file_name="the_weight_of_words.txt"
            )

            # Optional debug
            if show_debug:
                st.markdown("#### Debug: draft")
                st.code(out.poem)
                st.markdown("#### Debug: critique (hidden by default)")
                st.json(out.critique)

    if btn_again:
        last_req = st.session_state["last_request"]
        base_poem = st.session_state["last_revised"] or st.session_state["last_poem"]

        out = improve_again(llm, last_req, base_poem)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_critique"] = out.critique
            st.session_state["last_revised"] = out.revised_poem

            # Simple output: show revised only
            st.code(out.revised_poem)

            st.download_button(
                "Download (.txt)", out.revised_poem, file_name="the_weight_of_words.txt"
            )

            # Optional debug
            if show_debug:
                st.markdown("#### Debug: critique (hidden by default)")
                st.json(out.critique)

# Footer: keep the session preview minimal
st.divider()
if st.session_state["last_revised"]:
    st.caption("Latest revised poem (session):")
    st.code(st.session_state["last_revised"])
