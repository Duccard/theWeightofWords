import uuid
import streamlit as st
from dotenv import load_dotenv

from core.config import load_config
from core.logging_setup import setup_logger
from core.llm_factory import create_llm
from core.orchestrator import generate_only, generate_and_improve, improve_again
from agent.schemas import PoemRequest
from core.storage import get_storage

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

load_dotenv()
logger = setup_logger()

st.set_page_config(
    page_title="The Weight of Words",
    layout="wide",
)

st.markdown(
    """
    <style>
    h1 {
        font-family: "Brush Script MT", cursive;
        font-size: 3rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("The Weight of Words")
st.caption("A personalized poem generator")

# -------------------------------------------------------------------
# Config + storage
# -------------------------------------------------------------------

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

# Stable session user
if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

# -------------------------------------------------------------------
# Session defaults
# -------------------------------------------------------------------

defaults = {
    "poem_name": "Untitled",
    "versions": [],
    "rated_versions": set(),
    "adv_model": "gpt-4o-mini",
    "adv_temperature": 0.9,
    "adv_top_p": 0.95,
    "adv_apply_prefs": True,
    "adv_use_people": True,
    "adv_show_injected_memory": False,
    "adv_show_debug": False,
    "adv_show_cost": False,
}

for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# -------------------------------------------------------------------
# Memory builder (FIX)
# -------------------------------------------------------------------


def build_user_memory(storage_obj, user_id, include_prefs=True, include_people=True):
    parts = []

    if include_prefs:
        taste = storage_obj.get_taste_profile(user_id) or {}
        total = int(taste.get("total_ratings", 0) or 0)

        if total <= 0:
            parts.append("Preferences learned from ratings: none yet.")
        else:
            rhyme_score = float(taste.get("prefer_rhyme_score", 0.0) or 0.0)
            rhyme_hint = (
                "prefers rhyme"
                if rhyme_score > 1
                else (
                    "prefers no rhyme"
                    if rhyme_score < -1
                    else "no strong rhyme preference"
                )
            )

            avg_lines = taste.get("avg_line_count")
            avg_lines = str(int(avg_lines)) if avg_lines else "unknown"

            parts.append(
                "Preferences learned from ratings:\n"
                f"- {rhyme_hint}\n"
                f"- typical length: ~{avg_lines} lines"
            )

    if include_people:
        people = storage_obj.list_people(user_id) or []
        if not people:
            parts.append("People memory: none yet.")
        else:
            lines = [
                f"- {p['name']} ({p['relationship']})"
                + (f" — {p['note']}" if p.get("note") else "")
                for p in people[:10]
            ]
            parts.append("People memory:\n" + "\n".join(lines))

    return "\n\n".join(parts).strip()


# -------------------------------------------------------------------
# Tabs
# -------------------------------------------------------------------

tab_write, tab_people, tab_adv = st.tabs(["Write", "People", "Advanced"])

# -------------------------------------------------------------------
# WRITE TAB
# -------------------------------------------------------------------

with tab_write:
    st.subheader("Write")

    poem_name = st.text_input("Poem name", value=st.session_state["poem_name"])
    st.session_state["poem_name"] = poem_name

    theme = st.text_area("Theme / background", height=120)

    style = st.selectbox(
        "Format",
        ["free_verse", "haiku", "sonnet_like", "spoken_word"],
    )

    line_count = st.slider("Length (lines)", 4, 60, 12)

    user_memory = ""
    if st.session_state["adv_apply_prefs"] or st.session_state["adv_use_people"]:
        user_memory = build_user_memory(
            storage,
            USER_ID,
            include_prefs=st.session_state["adv_apply_prefs"],
            include_people=st.session_state["adv_use_people"],
        )

    if st.session_state["adv_show_injected_memory"]:
        st.code(user_memory)

    if st.button("Generate poem"):
        req = PoemRequest(
            poem_name=poem_name,
            theme=theme,
            style=style,
            line_count=line_count,
            user_memory=user_memory,
        )

        llm = create_llm(
            cfg,
            model=st.session_state["adv_model"],
            temperature=st.session_state["adv_temperature"],
            top_p=st.session_state["adv_top_p"],
        )

        poem, meta = generate_only(llm, req)

        st.session_state["versions"].append({"text": poem, "meta": meta})

    # ---- Show versions + rating ----
    for i, v in enumerate(st.session_state["versions"]):
        st.markdown(f"### Version {i + 1}")
        st.text(v["text"])

        if i not in st.session_state["rated_versions"]:
            rating = st.radio(
                "Rate this version",
                [1, 2, 3, 4, 5],
                horizontal=True,
                key=f"rate_{i}",
            )
            if st.button("Submit rating", key=f"submit_{i}"):
                storage.add_rating(
                    USER_ID,
                    poem_name,
                    v["text"],
                    rating,
                )
                st.session_state["rated_versions"].add(i)
                st.success("Thanks for the feedback!")

# -------------------------------------------------------------------
# PEOPLE TAB
# -------------------------------------------------------------------

with tab_people:
    st.subheader("People memory")

    with st.form("add_person", clear_on_submit=True):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship")
        note = st.text_area("Note", height=80)
        submitted = st.form_submit_button("Save")

    if submitted:
        storage.add_person(USER_ID, name, relationship, note)
        st.success("Saved.")

    st.divider()
    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")
    else:
        for p in people:
            st.markdown(f"**{p['name']}** — {p['relationship']}")
            if p.get("note"):
                st.caption(p["note"])

# -------------------------------------------------------------------
# ADVANCED TAB
# -------------------------------------------------------------------

with tab_adv:
    st.subheader("Advanced settings")

    st.markdown("### Personalization")
    st.session_state["adv_apply_prefs"] = st.toggle(
        "Apply my preferences", st.session_state["adv_apply_prefs"]
    )
    st.session_state["adv_use_people"] = st.toggle(
        "Use people memory", st.session_state["adv_use_people"]
    )
    st.session_state["adv_show_injected_memory"] = st.toggle(
        "Show injected memory", st.session_state["adv_show_injected_memory"]
    )

    st.divider()
    st.markdown("### Model")
    st.session_state["adv_model"] = st.selectbox(
        "Model",
        ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o"],
    )
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, st.session_state["adv_temperature"], 0.1
    )
    st.session_state["adv_top_p"] = st.slider(
        "Top-p", 0.1, 1.0, st.session_state["adv_top_p"], 0.05
    )

    st.divider()
    st.markdown("### Debug / cost")
    st.session_state["adv_show_cost"] = st.toggle(
        "Show token cost (experimental)",
        st.session_state["adv_show_cost"],
    )
