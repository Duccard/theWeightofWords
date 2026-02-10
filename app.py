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
st.caption(
    "Generate poems with constraints. Improve them with critique loops. (Option B)"
)

try:
    cfg = load_config()
except Exception as e:
    st.error(str(e))
    st.stop()

st.sidebar.header("Model Settings")
model = st.sidebar.selectbox(
    "Model", ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"], index=0
)
temperature = st.sidebar.slider("Temperature", 0.0, 1.5, 0.9, 0.1)
top_p = st.sidebar.slider("Top-p", 0.1, 1.0, 0.95, 0.05)

llm = create_llm(cfg, model=model, temperature=temperature, top_p=top_p)

for k in ["last_request", "last_poem", "last_critique", "last_revised"]:
    st.session_state.setdefault(k, None)

left, right = st.columns([1, 1])

with left:
    st.subheader("Request")

    occasion = st.selectbox(
        "Occasion",
        [
            "birthday",
            "anniversary",
            "wedding",
            "graduation",
            "apology",
            "goodbye",
            "valentine",
            "just for fun",
        ],
        index=7,
    )
    theme = st.text_input("Theme", value="a late-night walk in winter")
    audience = st.text_input("Audience (optional)", value="a close friend")

    style = st.selectbox(
        "Style",
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
    writer_vibe = st.text_input(
        "Writer vibe (optional)", value="classical storyteller energy (no copying)"
    )

    must_include = st.text_input("Must include (comma-separated)", value="")
    avoid = st.text_input("Avoid (comma-separated)", value="")

    line_count = st.slider("Line count (ignored for strict forms)", 2, 60, 12)
    rhyme = st.checkbox("Rhyme", value=False)
    syllable_hints = st.text_input("Syllable hints (optional)", value="")
    no_cliches = st.checkbox("No clichés mode", value=True)
    reading_level = st.selectbox(
        "Reading level", ["simple", "general", "advanced"], index=1
    )

    acrostic_word = None
    if style == "acrostic":
        acrostic_word = st.text_input("Acrostic word", value="WINTER")

    req = PoemRequest(
        occasion=occasion,
        theme=(theme.strip() or "a meaningful moment"),
        audience=(audience.strip() or None),
        style=style,
        tone=tone,
        writer_vibe=(writer_vibe.strip() or None),
        must_include=[w.strip() for w in must_include.split(",") if w.strip()],
        avoid=[w.strip() for w in avoid.split(",") if w.strip()],
        line_count=line_count,
        rhyme=rhyme,
        syllable_hints=(syllable_hints.strip() or None),
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

with right:
    st.subheader("Output")

    if btn_fast:
        out = generate_only(llm, req)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = None
            st.session_state["last_revised"] = None

            st.markdown("### Draft")
            st.code(out.poem)

    if btn_full:
        out = generate_and_improve(llm, req)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = out.critique
            st.session_state["last_revised"] = out.revised_poem

            st.markdown("### Draft")
            st.code(out.poem)

            st.markdown("### Critique")
            st.json(out.critique)

            st.markdown("### Revised")
            st.code(out.revised_poem)

            st.download_button(
                "Download revised (.txt)",
                out.revised_poem,
                file_name="the_weight_of_words.txt",
            )

    if btn_again:
        last_req = st.session_state["last_request"]
        base_poem = st.session_state["last_revised"] or st.session_state["last_poem"]

        out = improve_again(llm, last_req, base_poem)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_critique"] = out.critique
            st.session_state["last_revised"] = out.revised_poem

            st.markdown("### Critique (new)")
            st.json(out.critique)

            st.markdown("### Revised (new)")
            st.code(out.revised_poem)

            st.download_button(
                "Download revised (.txt)",
                out.revised_poem,
                file_name="the_weight_of_words.txt",
            )

st.divider()
if st.session_state["last_revised"]:
    st.caption("Latest revised poem (session):")
    st.code(st.session_state["last_revised"])
