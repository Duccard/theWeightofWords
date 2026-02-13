import uuid
import streamlit as st
from dotenv import load_dotenv
import tiktoken

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

st.set_page_config(page_title="The Weight of Words", page_icon="📜", layout="wide")
st.title("The Weight of Words")
st.caption("Beautiful poem generator")

# -------------------------------------------------------------------
# Config
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
# Session state defaults
# -------------------------------------------------------------------

defaults = {
    "versions": [],
    "rated_versions": set(),
    "poem_name": "Untitled",
    "adv_model": "gpt-4o-mini",
    "adv_temperature": 0.9,
    "adv_top_p": 0.95,
    "adv_apply_prefs": True,
    "adv_use_people": True,
    "adv_show_injected_memory": False,
    "adv_rhyme": False,
    "adv_no_cliches": True,
    "adv_reading_level": "general",
    "adv_audience": "",
    "adv_help_bot": False,
    "adv_show_usage": False,
    "adv_price_in_per_1m": 0.0,
    "adv_price_out_per_1m": 0.0,
    "help_messages": [],
}

for k, v in defaults.items():
    st.session_state.setdefault(k, v)

# -------------------------------------------------------------------
# Token utilities
# -------------------------------------------------------------------


def _enc_for_model(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def estimate_tokens(model: str, text: str) -> int:
    enc = _enc_for_model(model)
    return len(enc.encode(text or ""))


def estimate_cost_usd(input_tokens, output_tokens, price_in, price_out):
    return (input_tokens / 1_000_000) * price_in + (
        output_tokens / 1_000_000
    ) * price_out


# -------------------------------------------------------------------
# Tabs
# -------------------------------------------------------------------

tab_write, tab_people, tab_advanced = st.tabs(["Write", "People", "Advanced"])

# -------------------------------------------------------------------
# Advanced tab
# -------------------------------------------------------------------

with tab_advanced:
    st.subheader("Advanced settings")

    st.markdown("### Personalization")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.session_state["adv_apply_prefs"] = st.toggle(
            "Apply my preferences", st.session_state["adv_apply_prefs"]
        )
    with c2:
        st.session_state["adv_use_people"] = st.toggle(
            "Use people memory", st.session_state["adv_use_people"]
        )
    with c3:
        st.session_state["adv_show_injected_memory"] = st.toggle(
            "Show injected memory", st.session_state["adv_show_injected_memory"]
        )

    st.markdown("### Constraints")
    c4, c5, c6 = st.columns(3)
    with c4:
        st.session_state["adv_rhyme"] = st.checkbox(
            "Rhyme", st.session_state["adv_rhyme"]
        )
    with c5:
        st.session_state["adv_no_cliches"] = st.checkbox(
            "No clichés", st.session_state["adv_no_cliches"]
        )
    with c6:
        st.session_state["adv_reading_level"] = st.selectbox(
            "Reading level", ["simple", "general", "advanced"], index=1
        )

    st.text_input(
        "Audience (optional)",
        value=st.session_state["adv_audience"],
        key="adv_audience",
        help="Helps the model adapt tone and references.",
    )

    st.divider()
    st.markdown("### Model")
    st.session_state["adv_model"] = st.selectbox(
        "Model", ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini"]
    )
    st.session_state["adv_temperature"] = st.slider(
        "Temperature", 0.0, 1.5, st.session_state["adv_temperature"], 0.1
    )
    st.session_state["adv_top_p"] = st.slider(
        "Top-p", 0.1, 1.0, st.session_state["adv_top_p"], 0.05
    )

    st.divider()
    st.markdown("### Tools")

    c7, c8 = st.columns(2)
    with c7:
        st.session_state["adv_help_bot"] = st.toggle(
            "Enable help chatbot", st.session_state["adv_help_bot"]
        )
    with c8:
        st.session_state["adv_show_usage"] = st.toggle(
            "Show token & cost", st.session_state["adv_show_usage"]
        )

    if st.session_state["adv_show_usage"]:
        st.caption("Optional cost estimation (user-supplied pricing).")
        p1, p2 = st.columns(2)
        with p1:
            st.session_state["adv_price_in_per_1m"] = st.number_input(
                "Input $ / 1M tokens",
                min_value=0.0,
                value=st.session_state["adv_price_in_per_1m"],
            )
        with p2:
            st.session_state["adv_price_out_per_1m"] = st.number_input(
                "Output $ / 1M tokens",
                min_value=0.0,
                value=st.session_state["adv_price_out_per_1m"],
            )

    # ---------------- Help chatbot ----------------

    if st.session_state["adv_help_bot"]:
        st.divider()
        st.markdown("### Help chatbot")

        if not st.session_state["help_messages"]:
            st.session_state["help_messages"] = [
                {
                    "role": "system",
                    "content": (
                        "You are the help assistant for The Weight of Words. "
                        "Explain how to use the Write tab, People memory, Advanced settings, ratings, and Improve Again."
                    ),
                }
            ]

        for m in st.session_state["help_messages"]:
            if m["role"] != "system":
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])

        q = st.chat_input("Ask how something works…")
        if q:
            st.session_state["help_messages"].append({"role": "user", "content": q})

            help_llm = create_llm(
                cfg,
                model="gpt-4o-mini",
                temperature=0.2,
                top_p=1.0,
            )

            convo = "\n".join(
                f"{m['role']}: {m['content']}"
                for m in st.session_state["help_messages"]
                if m["role"] != "system"
            )

            resp = help_llm.invoke(convo)
            answer = getattr(resp, "content", str(resp))

            st.session_state["help_messages"].append(
                {"role": "assistant", "content": answer}
            )
            st.rerun()

# -------------------------------------------------------------------
# Write tab
# -------------------------------------------------------------------

with tab_write:
    st.subheader("Write")

    poem_name = st.text_input("Poem name", value=st.session_state["poem_name"])
    st.session_state["poem_name"] = poem_name

    theme = st.text_area("Theme / background", height=120)

    style = st.selectbox(
        "Format", ["free_verse", "haiku", "sonnet_like", "spoken_word"]
    )
    line_count = st.slider("Length (lines)", 4, 60, 12)

    user_memory = ""
    if st.session_state["adv_apply_prefs"] or st.session_state["adv_use_people"]:
        user_memory = storage.build_user_memory(
            USER_ID,
            include_prefs=st.session_state["adv_apply_prefs"],
            include_people=st.session_state["adv_use_people"],
        )

    if st.session_state["adv_show_injected_memory"]:
        st.code(user_memory or "None")

    llm = create_llm(
        cfg,
        model=st.session_state["adv_model"],
        temperature=st.session_state["adv_temperature"],
        top_p=st.session_state["adv_top_p"],
    )

    if st.button("Generate"):
        req = PoemRequest(
            theme=theme,
            style=style,
            line_count=line_count,
            tone="warm",
        )

        proxy_prompt = f"{theme}\n{user_memory}"
        in_tokens = estimate_tokens(st.session_state["adv_model"], proxy_prompt)

        out = generate_and_improve(llm, req, user_memory=user_memory)

        if out.ok:
            st.session_state["versions"].append(out.revised)

            out_tokens = estimate_tokens(st.session_state["adv_model"], out.revised)

            if st.session_state["adv_show_usage"]:
                cost = estimate_cost_usd(
                    in_tokens,
                    out_tokens,
                    st.session_state["adv_price_in_per_1m"],
                    st.session_state["adv_price_out_per_1m"],
                )
                st.info(
                    f"Tokens — in: {in_tokens:,}, out: {out_tokens:,}, total: {in_tokens+out_tokens:,}"
                    + (f" | est. cost: ${cost:.4f}" if cost > 0 else "")
                )

    for i, v in enumerate(st.session_state["versions"], 1):
        st.markdown(f"### Version {i}")
        st.markdown(v)
