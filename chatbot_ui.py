import streamlit as st
import streamlit.components.v1 as components
from chatbot_agent_v2 import stream_chat_response

GREETING = "안녕하세요! 자산·임대차 계약·렌트롤·공실 현황 등 DB 데이터에 대해 물어보세요."

_fragment = getattr(st, "fragment", getattr(st, "experimental_fragment", lambda f: f))


def _safe_md(text: str) -> str:
    # Streamlit 마크다운은 '~' 한 쌍을 취소선으로 처리하므로 '10~12월' 같은 범위 표기가 깨지지 않게 이스케이프
    return text.replace("~", "\\~")


def _scroll_chat_to_bottom():
    """고정 높이(450px) 채팅 컨테이너를 맨 아래로 자동 스크롤합니다."""
    components.html(
        """
        <script>
        (function() {
            try {
                const doc = window.parent.document;
                const sidebar = doc.querySelector('[data-testid="stSidebar"]');
                if (!sidebar) return;
                sidebar.querySelectorAll('div').forEach(el => {
                    if (el.scrollHeight > el.clientHeight + 20 && el.clientHeight >= 300 && el.clientHeight <= 520) {
                        el.scrollTop = el.scrollHeight;
                    }
                });
            } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )


@_fragment
def _render_chatbot_fragment():
    st.markdown("---")
    head_l, head_r = st.columns([4, 1])
    head_l.markdown("### 💬 DB Data Q&A 챗봇")
    if head_r.button("🗑️", help="대화 초기화", key="chatbot_reset"):
        st.session_state["chat_history"] = [{"role": "assistant", "content": GREETING}]
    st.caption("예: 본점 공실률 / 다음달 렌트프리 업체 / 올해 부산 임대료 수입 / 3개월 내 만기 계약")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = [{"role": "assistant", "content": GREETING}]

    user_input = st.chat_input("질문을 입력하세요...", key="sidebar_chat_input")

    chat_container = st.container(height=450)
    with chat_container:
        for msg in st.session_state["chat_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(_safe_md(msg["content"]))

        if user_input:
            prior = [m for m in st.session_state["chat_history"] if m["content"] != GREETING]
            st.session_state["chat_history"].append({"role": "user", "content": user_input})

            with st.chat_message("user"):
                st.markdown(_safe_md(user_input))
            with st.chat_message("assistant"):
                status_ph = st.empty()
                text_ph = st.empty()
                status_ph.caption("💭 질문을 분석하는 중...")
                answer = ""
                for kind, payload in stream_chat_response(user_input, prior):
                    if kind == "status":
                        status_ph.caption(payload)
                    elif kind == "reset":
                        answer = ""
                        text_ph.empty()
                    elif kind == "delta":
                        status_ph.empty()
                        answer += payload
                        text_ph.markdown(_safe_md(answer) + "▌")
                status_ph.empty()
                text_ph.markdown(_safe_md(answer))

            st.session_state["chat_history"].append({"role": "assistant", "content": answer})
            _scroll_chat_to_bottom()


def render_chatbot():
    with st.sidebar:
        _render_chatbot_fragment()
