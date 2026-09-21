import sys
import os
import pandas as pd

sys.path.append(os.getcwd())
import chatbot_agent_v2

history = "[]"
msg = "10월 본점 렌트프리 업체 알려줘"

print("--- Testing Chatbot Logic ---")
print("User Msg:", msg)

response = chatbot_agent_v2.generate_chat_response(msg, history)
print("\n--- FINAL RESPONSE ---")
print(response)
