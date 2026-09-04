import time

def get_ai_response(user_text, user_code):
    """
    Input: User's verbal output(text form)+ user's coding output
    Output: AI's textual response
    """
    # simulating latency
    time.sleep(1) 
    # TODO: Insert Groq/OpenAI API
    return f"From your code{user_code[:10]}, I noticed a logical error. Could you explain why you used dynamic programming?"
