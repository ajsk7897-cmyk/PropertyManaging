import chatbot_agent_v2

history = "[]"
msg = "10월 본점 렌트프리 업체 알려줘"
print("Calling generate_chat_response...")
try:
    response = chatbot_agent_v2.generate_chat_response(msg, history)
    print("Response received:", response)
except Exception as e:
    print("Error:", e)
