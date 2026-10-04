import chatbot_agent_v2
import google.generativeai as genai
import logging
logging.basicConfig(level=logging.DEBUG)

def test():
    print("Testing generate_chat_response...")
    msg = "10월 본점 렌트프리 업체 알려줘"
    try:
        response = chatbot_agent_v2.generate_chat_response(msg, "")
        print("Response received:", response)
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test()
