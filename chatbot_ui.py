import streamlit as st
from chatbot_agent_v2 import generate_chat_response

def render_chatbot():
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 💬 DB Data Q&A 챗봇")
    st.sidebar.caption("부동산 자산, 임대차 계약, 렌트롤 현황에 대해 자유롭게 물어보세요!")
    
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = [
            {"role": "assistant", "content": "안녕하세요! 데이터베이스에 있는 자산이나 업체의 임대료, 면적 현황 등을 찾아드릴게요."}
        ]
        
    # 사이드바 내 스크롤 가능한 컨테이너
    chat_container = st.sidebar.container(height=450)
    
    with chat_container:
        for msg in st.session_state["chat_history"]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                
    user_input = st.sidebar.chat_input("질문을 입력하세요... (예: A자산 총 임대료)")
    
    if user_input:
        st.session_state["chat_history"].append({"role": "user", "content": user_input})
        with chat_container:
            with st.chat_message("user"):
                st.markdown(user_input)
                
            with st.chat_message("assistant"):
                with st.spinner("DB를 조회하고 답변을 생성하는 중..."):
                    recent_history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state["chat_history"][-5:-1]])
                    response = generate_chat_response(user_input, recent_history)
                    st.markdown(response)
                    
        st.session_state["chat_history"].append({"role": "assistant", "content": response})
