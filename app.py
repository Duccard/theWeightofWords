import uuid
import streamlit as st
from dotenv import load_dotenv

from core.config import load_config
from core.logging_setup import setup_logger
from core.llm_factory import create_llm
from core.orchestrator import generate_only, generate_and_improve, improve_again
from agent.schemas import PoemRequest
from core.storage import get_storage

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

# ---- Storage init (cloud-ready) ----
storage = get_storage()
try:
    storage.init()
except Exception as e:
    st.error(f"Storage init failed: {e}")
    st.stop()

# simple "user id" for now (until auth). Stable per browser session.
if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

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

STAR_OPTIONS = [1, 2, 3, 4, 5]


def stars_label(n: int) -> str:
    return "⭐" * n + "☆" * (5 - n)


main_tabs = st.tabs(["Write", "People", "Advanced"])

# ================= ADVANCED =================
with main_tabs[2]:
    st.subheader("Advanced settings")

    st.caption(f"Storage backend: **{storage.backend_name()}**")
    taste = storage.get_taste_profile(USER_ID)
    st.markdown("### Your taste profile (learned)")
    st.json(taste)

    st.divider()
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
    show_debug = st.checkbox("Show internal debug", value=False)

llm = create_llm(cfg, model=model, temperature=temperature, top_p=top_p)

# ================= PEOPLE =================
with main_tabs[1]:
    st.subheader("People (memory)")

    with st.form("add_person_form", clear_on_submit=True):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship (friend/partner/boss/etc.)")
        note = st.text_area(
            "Note (optional) — e.g., likes cats, hates cheesy lines", height=80
        )
        submitted = st.form_submit_button("Save person")

    if submitted:
        try:
            storage.add_person(USER_ID, name=name, relationship=relationship, note=note)
            st.success("Saved.")
        except Exception as e:
            st.error(str(e))

    st.divider()
    st.markdown("### Saved people")
    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")
    else:
        for p in people:
            st.markdown(f"**{p['name']}** — *{p['relationship']}*")
            if p.get("note"):
                st.caption(p["note"])

# ================= WRITE =================
with main_tabs[0]:
    st.subheader("Write")

    poem_name = st.text_input(
        "Poem Name",
        value=(st.session_state["poem_name"] or "Untitled"),
        help="Used for downloads and grouping versions.",
    )
    st.session_state["poem_name"] = poem_name

    theme_bg = st.text_area(
        "Theme / Background",
        height=120,
        value="Write a sincere poem with specific details.",
    )

    writer_style_choice = st.selectbox(
        "Writer Style", list(WRITER_STYLES.keys()), index=0
    )
    custom_writer_vibe = None
    if WRITER_STYLES.get(writer_style_choice) == "CUSTOM":
        custom_writer_vibe = st.text_input(
            "Custom writer vibe", value="classical storyteller energy (no copying)"
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

    if WRITER_STYLES.get(writer_style_choice) == "CUSTOM":
        writer_vibe = (custom_writer_vibe or "").strip() or None
    else:
        writer_vibe = WRITER_STYLES.get(writer_style_choice)

    must_list = [w.strip() for w in must_include.split(",") if w.strip()]
    avoid_list = [w.strip() for w in avoid.split(",") if w.strip()]
    syllable_val = syllable_hints.strip() or None
    audience_val = audience.strip() or None

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

    def render_versions():
        if not st.session_state["versions"]:
            st.info("No versions yet. Click Generate.")
            return

        safe_title = (poem_name.strip() or "Untitled").replace("/", "-")
        for i, v in enumerate(st.session_state["versions"], start=1):
            label = v["label"]
            text = v["text"]
            st.markdown(f"### {label}")
            st.code(text)
            st.download_button(
                f"Download {label} (.txt)",
                text,
                file_name=f"{safe_title} - {label}.txt",
                key=f"dl_{i}",
            )

    def rating_form(version_label: str, poem_text: str):
        st.divider()
        st.subheader(f"Rate {version_label}")

        form_key = (
            f"rate_{version_label}".replace(" ", "_").replace("(", "").replace(")", "")
        )
        rating_key = f"rating_{form_key}"
        feedback_key = f"feedback_{form_key}"
        ending_key = f"ending_{form_key}"

        with st.form(key=form_key, clear_on_submit=False):
            rating = st.radio(
                "Rating",
                STAR_OPTIONS,
                index=3,
                format_func=stars_label,
                horizontal=True,
                key=rating_key,
            )
            ending_pref = st.selectbox(
                "Ending preference (optional)",
                ["", "soft", "twist", "punchline", "hopeful"],
                index=0,
                key=ending_key,
            )
            feedback = st.text_area("Optional feedback", key=feedback_key)
            submitted = st.form_submit_button("Submit rating")

        if submitted:
            try:
                storage.add_rating(
                    user_id=USER_ID,
                    poem_name=poem_name,
                    version_label=version_label,
                    request=req.model_dump(),
                    poem_text=poem_text,
                    rating=int(st.session_state[rating_key]),
                    ending_pref=(st.session_state[ending_key] or None),
                    feedback=(st.session_state[feedback_key] or None),
                )
                storage.update_taste_profile(
                    user_id=USER_ID,
                    request=req.model_dump(),
                    rating=int(st.session_state[rating_key]),
                    ending_pref=(st.session_state[ending_key] or None),
                )
                st.success(
                    f"Saved rating: {stars_label(int(st.session_state[rating_key]))}"
                )
            except Exception as e:
                st.error(str(e))

    # Generate only => Version 1
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
            rating_form("Version 1", out.poem)

    # Generate + Improve => Version 1 + Version 2 (Upgraded)
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
                {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
            ]
            render_versions()
            rating_form("Version 2 (Upgraded)", out.revised_poem)

            if show_debug:
                st.markdown("#### Debug: critique (hidden by default)")
                st.json(out.critique)

    # Improve again => append Version N (Upgraded)
    if btn_again:
        last_req = st.session_state["last_request"]
        base_poem = st.session_state["versions"][-1]["text"]

        out = improve_again(llm, last_req, base_poem)
        if not out.ok:
            st.error(out.error_user)
        else:
            new_text = out.revised_poem.strip()
            prev_text = base_poem.strip()

            if new_text == prev_text:
                st.error(
                    "Improve again produced the same poem. Try again (or adjust constraints)."
                )
            else:
                st.session_state["last_critique"] = out.critique
                st.session_state["last_revised"] = out.revised_poem

                next_num = len(st.session_state["versions"]) + 1
                label = f"Version {next_num} (Upgraded)"
                st.session_state["versions"].append(
                    {"label": label, "text": out.revised_poem}
                )

                render_versions()
                rating_form(label, out.revised_poem)

                if show_debug:
                    st.markdown("#### Debug: critique (hidden by default)")
                    st.json(out.critique)

    if not (btn_fast or btn_full or btn_again):
        render_versions()
