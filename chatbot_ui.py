import streamlit as st
from chatbot_agent_v2 import stream_chat_response

GREETING = "안녕하세요! 자산·임대차 계약·렌트롤·공실 현황 등 DB 데이터에 대해 물어보세요."


def _safe_md(text: str) -> str:
    # Streamlit 마크다운은 '~' 한 쌍을 취소선으로 처리하므로 '10~12월' 같은 범위 표기가 깨지지 않게 이스케이프
    return text.replace("~", "\\~")


def render_chatbot():
    st.sidebar.markdown("---")
    head_l, head_r = st.sidebar.columns([4, 1])
    head_l.markdown("### 💬 DB Data Q&A 챗봇")
    if head_r.button("🗑️", help="대화 초기화", key="chatbot_reset"):
        st.session_state["chat_history"] = [{"role": "assistant", "content": GREETING}]
    st.sidebar.caption("예: 본점 공실률 / 다음달 렌트프리 업체 / 올해 부산 임대료 수입 / 3개월 내 만기 계약")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = [{"role": "assistant", "content": GREETING}]

    chat_container = st.sidebar.container(height=450)
    with chat_container:
        for msg in st.session_state["chat_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(_safe_md(msg["content"]))

    user_input = st.sidebar.chat_input("질문을 입력하세요...")
    if not user_input:
        return

    # 인사말은 모델 컨텍스트에서 제외
    prior = [m for m in st.session_state["chat_history"] if m["content"] != GREETING]
    st.session_state["chat_history"].append({"role": "user", "content": user_input})

    with chat_container:
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
