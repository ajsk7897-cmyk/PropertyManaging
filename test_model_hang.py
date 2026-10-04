import google.generativeai as genai
import os
import chatbot_agent_v2

print("Testing model...")
api_key = chatbot_agent_v2.get_gemini_api_key()
genai.configure(api_key=api_key)

try:
    model = genai.GenerativeModel('gemini-3.5-flash-lite')
    chat = model.start_chat()
    print("Sending hello...")
    response = chat.send_message("hello")
    print("Response:", response.text)
except Exception as e:
    print("Error:", e)
