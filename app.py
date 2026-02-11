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
    # Each element: {"label": "Version 1", "text": "..."}
    st.session_state["versions"] = []

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

    # Hidden by default; critique JSON stays internal.
    show_debug = st.checkbox("Show internal debug (draft & critique)", value=False)

# Create LLM after advanced settings exist
llm = create_llm(cfg, model=model, temperature=temperature, top_p=top_p)

# -------------------- Write tab (simple) --------------------
with tabs[0]:
    st.subheader("Write")

    poem_name = st.text_input(
        "Poem Name",
        value=(st.session_state["poem_name"] or "Untitled"),
        help="This name will be used for downloads and version grouping.",
    )
    st.session_state["poem_name"] = poem_name

    theme_bg = st.text_area(
        "Theme / Background",
        value="Write a sincere apology poem. Make it specific and human.",
        height=120,
    )

    writer_style_choice = st.selectbox(
        "Writer Style", list(WRITER_STYLES.keys()), index=0
    )

    custom_writer_vibe = None
    if WRITER_STYLES.get(writer_style_choice) == "CUSTOM":
        custom_writer_vibe = st.text_input(
            "Custom writer vibe",
            value="classical storyteller energy (no copying)",
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

    # Build writer vibe
    if WRITER_STYLES.get(writer_style_choice) == "CUSTOM":
        writer_vibe = (custom_writer_vibe or "").strip() or None
    else:
        writer_vibe = WRITER_STYLES.get(writer_style_choice)

    # Convert advanced values
    must_list = [w.strip() for w in must_include.split(",") if w.strip()]
    avoid_list = [w.strip() for w in avoid.split(",") if w.strip()]
    syllable_val = syllable_hints.strip() or None
    audience_val = audience.strip() or None

    # Build request object
    req = PoemRequest(
        occasion=occasion,
        theme=theme_bg.strip() or "a meaningful moment",
        audience=audience_val,
        style=style,
        tone=tone,
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

    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    with c1:
        btn_fast = st.button("Generate only (fast)")
    with c2:
        btn_full = st.button("Generate + Improve", type="primary")
    with c3:
        btn_again = st.button(
            "Improve again", disabled=len(st.session_state["versions"]) == 0
        )
    with c4:
        btn_clear = st.button("Clear versions")

    if btn_clear:
        st.session_state["versions"] = []
        st.session_state["last_request"] = None
        st.session_state["last_poem"] = None
        st.session_state["last_critique"] = None
        st.session_state["last_revised"] = None
        st.rerun()

    st.divider()
    st.subheader("Output")

    # Helper: render versions
    def render_versions():
        if not st.session_state["versions"]:
            st.info("No versions yet. Click Generate.")
            return

        for i, v in enumerate(st.session_state["versions"], start=1):
            label = v["label"]
            text = v["text"]

            st.markdown(f"### {label}")
            st.code(text)

            safe_title = (poem_name.strip() or "Untitled").replace("/", "-")
            filename = f"{safe_title} - {label}.txt"
            st.download_button(
                f"Download {label} (.txt)", text, file_name=filename, key=f"dl_{i}"
            )

    # Generate only: adds Version 1
    if btn_fast:
        out = generate_only(llm, req)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = None
            st.session_state["last_revised"] = None
            st.session_state["versions"] = [{"label": "Version 1", "text": out.poem}]

            render_versions()

            # Ratings UI (visible)
            st.divider()
            st.subheader("Rate this poem (helps personalization)")
            rating = st.select_slider(
                "Rating", options=[1, 2, 3, 4, 5], value=4, key="rating_v1"
            )
            feedback = st.text_area("Optional feedback", key="feedback_v1")
            st.button("Save rating (coming Day 2 storage)", disabled=True)

    # Generate + Improve: Version 1 + Version 2 (Upgraded)
    if btn_full:
        out = generate_and_improve(llm, req)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = out.critique  # stored but hidden
            st.session_state["last_revised"] = out.revised_poem

            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Upgraded Version (Version 2)", "text": out.revised_poem},
            ]

            render_versions()

            # Ratings UI applies to the latest version shown (Version 2)
            st.divider()
            st.subheader("Rate the Upgraded Version (helps personalization)")
            rating = st.select_slider(
                "Rating", options=[1, 2, 3, 4, 5], value=4, key="rating_v2"
            )
            feedback = st.text_area("Optional feedback", key="feedback_v2")
            st.button("Save rating (coming Day 2 storage)", disabled=True)

            if show_debug:
                st.markdown("#### Debug: critique (hidden by default)")
                st.json(out.critique)

    # Improve again: append Version 3/4/5...
    if btn_again:
        last_req = st.session_state["last_request"]
        base_poem = st.session_state["versions"][-1]["text"]

        out = improve_again(llm, last_req, base_poem)
        if not out.ok:
            st.error(out.error_user)
        else:
            new_text = out.revised_poem.strip()
            prev_text = base_poem.strip()

            # Hard guard: if identical, show error (prevents violating your rule)
            if new_text == prev_text:
                st.error(
                    "Improve again produced the same poem. Try again (or adjust constraints)."
                )
            else:
                st.session_state["last_critique"] = out.critique  # stored but hidden
                st.session_state["last_revised"] = out.revised_poem

                next_num = len(st.session_state["versions"]) + 1
                st.session_state["versions"].append(
                    {"label": f"Version {next_num}", "text": out.revised_poem}
                )

                render_versions()

                # Rating UI for newest version
                st.divider()
                st.subheader(f"Rate Version {next_num} (helps personalization)")
                rating = st.select_slider(
                    "Rating",
                    options=[1, 2, 3, 4, 5],
                    value=4,
                    key=f"rating_v{next_num}",
                )
                feedback = st.text_area(
                    "Optional feedback", key=f"feedback_v{next_num}"
                )
                st.button("Save rating (coming Day 2 storage)", disabled=True)

                if show_debug:
                    st.markdown("#### Debug: critique (hidden by default)")
                    st.json(out.critique)

    # If no button clicked, still render existing versions
    if not (btn_fast or btn_full or btn_again):
        render_versions()
