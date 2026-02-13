import uuid
import streamlit as st
from dotenv import load_dotenv
from typing import Any, Iterable

from core.config import load_config
from core.logging_setup import setup_logger
from core.llm_factory import create_llm
from core.storage import get_storage
from core.orchestrator import agent  # adjust if named differently

# -------------------------------------------------------------------
# Setup
# -------------------------------------------------------------------

load_dotenv()
logger = setup_logger()

st.set_page_config(
    page_title="The Weight of Words",
    page_icon="📜",
    layout="wide",
)

# -------------------------------------------------------------------
# Styling (background + cursive title)
# -------------------------------------------------------------------

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] > .main {
        background-image: url("https://images.freepik.com/free-ai-image/mesmerizing-colorful-skies-illustration_381016425.jpg");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }

    h1 {
        font-family: "Brush Script MT", "Apple Chancery", cursive !important;
        letter-spacing: 0.5px;
    }

    [data-testid="stMainBlockContainer"] {
        background: rgba(255,255,255,0.82);
        border-radius: 18px;
        padding: 1.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("The Weight of Words")
st.caption("A thoughtful poetry agent")

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------


def build_user_memory(
    storage: Any,
    user_id: str,
    *,
    include_prefs: bool = True,
    include_people: bool = True,
) -> str:
    parts: list[str] = []

    # Preferences (safe, optional)
    if include_prefs:
        prefs = {}
        for fn_name in ("get_user_preferences", "get_prefs"):
            fn = getattr(storage, fn_name, None)
            if callable(fn):
                try:
                    prefs = fn(user_id)
                except Exception:
                    prefs = {}
                break

        if isinstance(prefs, dict) and prefs:
            lines = [f"- {k}: {v}" for k, v in prefs.items() if v]
            if lines:
                parts.append("USER PREFERENCES:\n" + "\n".join(lines))

    # People memory
    if include_people:
        people = []
        if hasattr(storage, "list_people"):
            try:
                people = storage.list_people(user_id)
            except Exception:
                people = []

        names = []
        for p in people:
            if isinstance(p, dict) and p.get("name"):
                names.append(p["name"])

        if names:
            parts.append("PEOPLE TO REMEMBER:\n- " + "\n- ".join(names))

    return "\n\n".join(parts).strip()


def extract_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for k in ("text", "content", "output", "final"):
            if k in result and isinstance(result[k], str):
                return result[k]
        msgs = result.get("messages")
        if isinstance(msgs, list) and msgs:
            last = msgs[-1]
            if isinstance(last, dict) and isinstance(last.get("content"), str):
                return last["content"]
            if hasattr(last, "content"):
                return str(last.content)
    if hasattr(result, "content"):
        return str(result.content)
    return str(result)


# -------------------------------------------------------------------
# Config + Storage
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

if "user_id" not in st.session_state:
    st.session_state["user_id"] = "user_" + str(uuid.uuid4())[:8]
USER_ID = st.session_state["user_id"]

# -------------------------------------------------------------------
# Session defaults
# -------------------------------------------------------------------

st.session_state.setdefault("versions", [])
st.session_state.setdefault("poem_text", "")
st.session_state.setdefault("poem_name", "Untitled")

# Advanced
st.session_state.setdefault("adv_model", "gpt-4o-mini")
st.session_state.setdefault("adv_temperature", 0.9)
st.session_state.setdefault("adv_top_p", 0.95)
st.session_state.setdefault("adv_apply_prefs", True)
st.session_state.setdefault("adv_use_people", True)
st.session_state.setdefault("adv_show_memory", False)

# -------------------------------------------------------------------
# Tabs
# -------------------------------------------------------------------

tab_write, tab_people, tab_advanced = st.tabs(["Write", "People", "Advanced"])

# ===========================
# ADVANCED
# ===========================

with tab_advanced:
    st.subheader("Advanced settings")

    st.session_state["adv_model"] = st.selectbox(
        "Model", ["gpt-4o-mini", "gpt-4o"], index=0
    )
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, st.session_state["adv_temperature"], 0.1
    )
    st.session_state["adv_top_p"] = st.slider(
        "Top-p", 0.1, 1.0, st.session_state["adv_top_p"], 0.05
    )

    st.divider()

    st.session_state["adv_apply_prefs"] = st.checkbox(
        "Apply my preferences", value=st.session_state["adv_apply_prefs"]
    )
    st.session_state["adv_use_people"] = st.checkbox(
        "Use people memory", value=st.session_state["adv_use_people"]
    )
    st.session_state["adv_show_memory"] = st.checkbox(
        "Show injected memory", value=st.session_state["adv_show_memory"]
    )

# Create LLM once
llm = create_llm(
    cfg,
    model=st.session_state["adv_model"],
    temperature=st.session_state["adv_temperature"],
    top_p=st.session_state["adv_top_p"],
)

# ===========================
# WRITE
# ===========================

with tab_write:
    st.subheader("Write")

    poem_name = st.text_input("Poem name", st.session_state["poem_name"])
    st.session_state["poem_name"] = poem_name

    theme = st.text_area("Theme / background", height=120)
    style = st.selectbox(
        "Format", ["free_verse", "haiku", "sonnet_like", "spoken_word"]
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

    if st.session_state["adv_show_memory"] and user_memory:
        st.code(user_memory)

    st.divider()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        gen_fast = st.button("⚡ Generate (fast)", use_container_width=True)
    with col2:
        gen = st.button("✨ Generate", use_container_width=True)
    with col3:
        improve = st.button("🛠 Improve", use_container_width=True)
    with col4:
        clear = st.button("🧹 Clear versions", use_container_width=True)

    if clear:
        st.session_state["versions"] = []
        st.session_state["poem_text"] = ""
        st.rerun()

    if gen_fast or gen:
        payload = {
            "theme": theme,
            "style": style,
            "line_count": line_count,
            "memory": user_memory,
            "mode": "fast" if gen_fast else "best",
        }
        result = agent.invoke(payload)
        text = extract_text(result).strip()
        if text:
            st.session_state["versions"].append(text)
            st.session_state["poem_text"] = text
            st.rerun()

    if improve and st.session_state["poem_text"]:
        payload = {
            "draft": st.session_state["poem_text"],
            "theme": theme,
            "style": style,
            "line_count": line_count,
            "memory": user_memory,
            "mode": "improve",
        }
        result = agent.invoke(payload)
        text = extract_text(result).strip()
        if text:
            st.session_state["versions"].append(text)
            st.session_state["poem_text"] = text
            st.rerun()

    st.text_area("Poem", st.session_state["poem_text"], height=360)

    if st.session_state["versions"]:
        st.markdown("### Versions")
        for i, v in enumerate(reversed(st.session_state["versions"]), 1):
            with st.expander(f"Version {len(st.session_state['versions']) - i + 1}"):
                st.code(v)

# ===========================
# PEOPLE
# ===========================

with tab_people:
    st.subheader("People")

    with st.form("add_person"):
        name = st.text_input("Name")
        relationship = st.text_input("Relationship")
        note = st.text_area("Note")
        submitted = st.form_submit_button("Save")

    if submitted and name:
        storage.add_person(USER_ID, name=name, relationship=relationship, note=note)
        st.success("Saved")

    st.divider()

    people = storage.list_people(USER_ID)
    if not people:
        st.info("No people saved yet.")
    else:
        for p in people:
            st.markdown(f"**{p['name']}** — {p.get('relationship','')}")
            if p.get("note"):
                st.caption(p["note"])
