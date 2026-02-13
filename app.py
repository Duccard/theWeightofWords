from __future__ import annotations

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

st.set_page_config(page_title="The Weight of Words", page_icon="📜", layout="centered")


def load_bg_image_base64(path: Path) -> str:
    if not path.exists():
        return ""
    return base64.b64encode(path.read_bytes()).decode("utf-8")


BG_PATH = Path.cwd() / "assets" / "background.jpg"
bg_base64 = load_bg_image_base64(BG_PATH)

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Great+Vibes&display=swap');

    /* ===== Background ===== */
    .stApp {{
        background-image: url("data:image/jpeg;base64,{bg_base64}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}

    /* ===== Make almost all text white ===== */
    html, body, .stApp, p, span, label,
    .stMarkdown, .stText, .stCaption, .stSubheader, .stHeader {{
        color: #ffffff !important;
    }}

    /* Tabs */
    button[data-baseweb="tab"] {{
        color: #ffffff !important;
        font-weight: 600;
    }}

    /* ===== Title styling (we'll render our own title below) ===== */
    .wow-title {{
        font-family: 'Great Vibes', cursive;
        font-size: 72px;
        text-align: center;
        color: #ffffff;
        margin: 0.2rem 0 0.2rem 0;
        line-height: 1.0;
    }}
    .wow-subtitle {{
        text-align: center;
        font-size: 1.1rem;
        opacity: 0.9;
        color: #ffffff;
        margin-bottom: 1.75rem;
    }}

    /* ===== Inputs: white field, black typed text ===== */
    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox div[role="combobox"],
    .stNumberInput input {{
        background: rgba(255,255,255,0.95) !important;
        color: #000000 !important;
        border-radius: 10px !important;
    }}

    /* Placeholder text a bit darker so it’s visible on white */
    .stTextInput input::placeholder,
    .stTextArea textarea::placeholder {{
        color: rgba(0,0,0,0.55) !important;
    }}

    /* ===== Poem output: translucent dark with white text ===== */
    pre, code {{
        background: rgba(0,0,0,0.38) !important;
        color: #ffffff !important;
        border-radius: 12px !important;
    }}

    /* ===== Fix Streamlit "info" boxes (blue) -> dark + white ===== */
    div[data-testid="stNotification"] {{
        background-color: rgba(0,0,0,0.55) !important;
        border: 1px solid rgba(255,255,255,0.18) !important;
    }}
    div[data-testid="stNotification"] p {{
        color: #ffffff !important;
    }}

    /* ===== Buttons =====
       We make Primary buttons orange.
       Then we ALSO force these components to look like primary:
       - Download buttons
       - Form submit buttons (Save person, Submit rating)
    */
    :root {{
        --wow-orange: #ff7a1a;
        --wow-orange-hover: #ff6a00;
    }}

    /* Primary buttons (Generate + Improve uses type="primary") */
    button[data-testid="baseButton-primary"] {{
        background-color: var(--wow-orange) !important;
        color: #ffffff !important;
        border: none !important;
    }}
    button[data-testid="baseButton-primary"]:hover {{
        background-color: var(--wow-orange-hover) !important;
        color: #ffffff !important;
        border: none !important;
    }}

    /* Download button -> make it orange like primary */
    .stDownloadButton > button {{
        background-color: var(--wow-orange) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
    }}
    .stDownloadButton > button:hover {{
        background-color: var(--wow-orange-hover) !important;
        color: #ffffff !important;
        border: none !important;
    }}

    /* Form submit buttons (Save person, Submit rating) -> orange */
    [data-testid="stFormSubmitButton"] > button {{
        background-color: var(--wow-orange) !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 10px !important;
    }}
    [data-testid="stFormSubmitButton"] > button:hover {{
        background-color: var(--wow-orange-hover) !important;
        color: #ffffff !important;
        border: none !important;
    }}

    /* Keep secondary buttons readable (Generate only, Improve again, Clear versions) */
    .stButton > button:not([data-testid="baseButton-primary"]) {{
        background: rgba(255,255,255,0.18) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.35) !important;
        border-radius: 10px !important;
    }}
    .stButton > button:not([data-testid="baseButton-primary"]):hover {{
        background: rgba(255,255,255,0.24) !important;
        color: #ffffff !important;
        border: 1px solid rgba(255,255,255,0.45) !important;
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

# ---- Storage init (cloud-ready) ----
storage = get_storage()
try:
    storage.init()
except Exception as e:
    st.error(f"Storage init failed: {e}")
    st.stop()

# stable per browser session (until auth)
if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

# ---- Writer style presets (removed custom option) ----
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
}

# ---- Session state ----
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
st.session_state.setdefault("adv_model", "gpt-4o-mini")
st.session_state.setdefault("adv_temperature", 0.9)
st.session_state.setdefault("adv_top_p", 0.95)

st.session_state.setdefault("adv_audience", "")

# Move these to advanced top
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
        total = int(taste.get("total_ratings", 0) or 0)

        if total <= 0:
            parts.append("Preferences learned from ratings: none yet.")
        else:
            rhyme_score = float(taste.get("prefer_rhyme_score", 0.0) or 0.0)
            if rhyme_score > 1:
                rhyme_hint = "prefers rhyme"
            elif rhyme_score < -1:
                rhyme_hint = "prefers no rhyme"
            else:
                rhyme_hint = "no strong rhyme preference"

            avg_lines = taste.get("avg_line_count", None)
            avg_lines_str = (
                str(int(avg_lines))
                if isinstance(avg_lines, (int, float))
                else "unknown"
            )
            reading_guess = taste.get("reading_level_guess") or "unknown"
            ending_guess = taste.get("ending_guess") or "unknown"

            parts.append(
                "Preferences learned from ratings:\n"
                f"- {rhyme_hint}\n"
                f"- typical length: ~{avg_lines_str} lines\n"
                f"- reading level: {reading_guess}\n"
                f"- ending style: {ending_guess}\n"
            )

    if include_people:
        ppl = storage_obj.list_people(user_id) or []
        if not ppl:
            parts.append("People memory: none yet.")
        else:
            lines = []
            for p in ppl[:10]:
                note = f" — note: {p['note']}" if p.get("note") else ""
                lines.append(f"- {p['name']} ({p['relationship']}){note}")
            parts.append("People memory:\n" + "\n".join(lines))

    return "\n\n".join(parts).strip() or "None"


def person_icon(relationship: str) -> str:
    rel = (relationship or "").lower()
    if "girlfriend" in rel or "boyfriend" in rel or "partner" in rel:
        return "❤️"
    if "friend" in rel:
        return "🧑‍🤝‍🧑"
    if "boss" in rel or "manager" in rel:
        return "🧑‍💼"
    if (
        "mom" in rel
        or "mother" in rel
        or "dad" in rel
        or "father" in rel
        or "parent" in rel
    ):
        return "👪"
    if "wife" in rel or "husband" in rel:
        return "💍"
    return "👤"


main_tabs = st.tabs(["Write", "People", "Advanced"])

# ================= ADVANCED =================
with main_tabs[2]:
    st.subheader("Advanced settings")
    st.caption(f"Storage backend: **{storage.backend_name()}**")

    st.markdown("### Personalization & constraints")
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        st.session_state["adv_apply_prefs"] = st.toggle(
            "Apply my preferences", value=bool(st.session_state["adv_apply_prefs"])
        )
    with c2:
        st.session_state["adv_use_people"] = st.toggle(
            "Use people memory", value=bool(st.session_state["adv_use_people"])
        )
    with c3:
        st.session_state["adv_show_injected_memory"] = st.toggle(
            "Show injected memory",
            value=bool(st.session_state["adv_show_injected_memory"]),
        )

    c4, c5, c6 = st.columns([1, 1, 1])
    with c4:
        st.session_state["adv_rhyme"] = st.checkbox(
            "Rhyme", value=bool(st.session_state["adv_rhyme"])
        )
    with c5:
        st.session_state["adv_no_cliches"] = st.checkbox(
            "No clichés mode", value=bool(st.session_state["adv_no_cliches"])
        )
    with c6:
        st.session_state["adv_reading_level"] = st.selectbox(
            "Reading level",
            ["simple", "general", "advanced"],
            index=(
                ["simple", "general", "advanced"].index(
                    st.session_state["adv_reading_level"]
                )
                if st.session_state["adv_reading_level"]
                in ["simple", "general", "advanced"]
                else 1
            ),
        )

    st.session_state["adv_audience"] = st.text_input(
        "Audience (optional) — who this is for / who will read it",
        value=st.session_state["adv_audience"],
        help="Helps the model choose references and vibe. Example: 'my friend group', 'my girlfriend', 'my boss'.",
    )

    st.divider()
    st.markdown("### Model")
    st.session_state["adv_model"] = st.selectbox(
        "Model",
        ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
        index=(
            ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"].index(
                st.session_state["adv_model"]
            )
            if st.session_state["adv_model"]
            in ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"]
            else 0
        ),
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
        "Syllable hints (optional)", value=st.session_state["adv_syllable_hints"]
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
        index=(
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
            ].index(st.session_state["adv_tone"])
            if st.session_state["adv_tone"]
            in [
                "warm",
                "funny",
                "romantic",
                "somber",
                "hopeful",
                "angry",
                "motivational",
                "surreal",
                "minimalist",
            ]
            else 0
        ),
    )
    st.session_state["adv_show_debug"] = st.checkbox(
        "Show internal debug", value=bool(st.session_state["adv_show_debug"])
    )

    st.divider()
    st.markdown("### Data")
    show_taste = st.checkbox("See my taste profile", value=False)
    if show_taste:
        taste = storage.get_taste_profile(USER_ID)
        st.json(taste)

    st.markdown("### Recent ratings (last 10)")
    try:
        recent = storage.list_ratings(USER_ID, limit=10)
        if not recent:
            st.info("No ratings yet.")
        else:
            st.dataframe(recent, use_container_width=True)
    except Exception as e:
        st.warning(f"Could not load ratings yet: {e}")

# LLM creation (always has defaults in session_state)
llm = create_llm(
    cfg,
    model=st.session_state["adv_model"],
    temperature=float(st.session_state["adv_temperature"]),
    top_p=float(st.session_state["adv_top_p"]),
)

# ================= PEOPLE =================
with main_tabs[1]:
    st.subheader("People")

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
            icon = person_icon(p.get("relationship") or "")
            st.markdown(f"{icon} **{p['name']}** — *{p['relationship']}*")
            if p.get("note"):
                st.caption(p["note"])

# ================= WRITE =================
with main_tabs[0]:
    st.subheader("Write")

    user_memory = build_user_memory(
        storage,
        USER_ID,
        include_prefs=bool(st.session_state["adv_apply_prefs"]),
        include_people=bool(st.session_state["adv_use_people"]),
    )

    if bool(st.session_state["adv_show_injected_memory"]):
        st.code(user_memory)

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
    writer_vibe = WRITER_STYLES.get(writer_style_choice)

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

    must_list = [
        w.strip() for w in st.session_state["adv_must_include"].split(",") if w.strip()
    ]
    avoid_list = [
        w.strip() for w in st.session_state["adv_avoid"].split(",") if w.strip()
    ]
    syllable_val = (st.session_state["adv_syllable_hints"] or "").strip() or None

    req = PoemRequest(
        occasion=occasion,
        theme=theme_bg.strip() or "a meaningful moment",
        audience=(st.session_state["adv_audience"].strip() or None),
        style=style,
        tone=st.session_state["adv_tone"],
        writer_vibe=writer_vibe,
        must_include=must_list,
        avoid=avoid_list,
        line_count=int(line_count),
        rhyme=bool(st.session_state["adv_rhyme"]),
        syllable_hints=syllable_val,
        no_cliches=bool(st.session_state["adv_no_cliches"]),
        reading_level=st.session_state["adv_reading_level"],
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
        st.session_state["rated_versions"] = set()
        st.session_state["last_request"] = None
        st.session_state["last_poem"] = None
        st.session_state["last_critique"] = None
        st.session_state["last_revised"] = None
        st.rerun()

    # ---- Button actions: update state then rerun ----
    if btn_fast:
        out = generate_only(llm, req, user_memory=user_memory)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = None
            st.session_state["last_revised"] = None
            st.session_state["versions"] = [{"label": "Version 1", "text": out.poem}]
            st.rerun()

    if btn_full:
        out = generate_and_improve(llm, req, user_memory=user_memory)
        if not out.ok:
            st.error(out.error_user)
        else:
            st.session_state["last_request"] = req
            st.session_state["last_poem"] = out.poem
            st.session_state["last_critique"] = out.critique
            st.session_state["last_revised"] = out.revised_poem
            st.session_state["versions"] = [
                {"label": "Version 1", "text": out.poem},
                {"label": "Version 2 (Upgraded)", "text": out.revised_poem},
            ]
            st.rerun()

    if btn_again:
        last_req = st.session_state["last_request"]
        base_poem = st.session_state["versions"][-1]["text"]

        out = improve_again(llm, last_req, base_poem, user_memory=user_memory)
        if not out.ok:
            st.error(out.error_user)
        else:
            new_text = (out.revised_poem or "").strip()
            prev_text = (base_poem or "").strip()

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
        if version_label in st.session_state["rated_versions"]:
            return

        st.divider()
        st.subheader(f"Rate {version_label}")

        form_key = (
            f"rate_{version_label}".replace(" ", "_").replace("(", "").replace(")", "")
        )
        rating_key = f"rating_{form_key}"
        feedback_key = f"feedback_{form_key}"
        ending_key = f"ending_{form_key}"

        with st.form(key=form_key, clear_on_submit=False):
            st.radio(
                "Rating",
                STAR_OPTIONS,
                index=3,
                format_func=stars_label,
                horizontal=True,
                key=rating_key,
            )
            st.selectbox(
                "Ending preference (optional)",
                ["", "soft", "twist", "punchline", "hopeful"],
                index=0,
                key=ending_key,
            )
            st.text_area("Optional feedback", key=feedback_key)
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

                st.session_state["rated_versions"].add(version_label)
                st.success(
                    f"Saved rating: {stars_label(int(st.session_state[rating_key]))}"
                )
                st.rerun()
            except Exception as e:
                st.error(str(e))

    render_versions()

    for v in st.session_state["versions"]:
        rating_form(v["label"], v["text"])

    if bool(st.session_state["adv_show_debug"]) and st.session_state.get(
        "last_critique"
    ):
        st.markdown("#### Debug: critique (hidden by default)")
        st.json(st.session_state["last_critique"])
