import os
import logging
import json
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configuration
PORT = int(os.getenv("PORT", "8080"))

basicConfig(level=logging.INFO, filename='log.info', 
filemode="%(actime)s - %(levelname)s - %(message)s") # Change 1 implement Logging 
logging.debug("debug")
logging.info("info")
logging.warning("Warning")
logging.error("error")
logging.critical("critical")

DOMAIN = os.getenv("NGROK_URL") # Change 2: Adds a safety check to public public-facing address
if not DOMAIN:
     raise ValueError("Missing NGROCK_URL in enviorment variables")
WS_URL = f"wss://{DOMAIN}/ws"

WELCOME_GREETING = "Hi! I am a voice assistant powered by Twilio and OpenAI.. Ask me anything!"
 
SYSTEM_PROMPT = ( # Change three: Fixed system_prompt formatting
    "You are a helpful assistant. This conversation is being translated to voice."
    "So answer carefully. When you respond, please spell out all numbers, for example, twenty, not 20. "
    "Do not include emojis in your responses. Do not include bullet points, asterisks, or special symbols."
)


# Initialize OpenAI client
openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Store active sessions
sessions = {}

# Create FastAPI app
app = FastAPI()

async def ai_response(messages):
    """Get a response from OpenAI API"""
    try: # Change four: Try except in case AI fails to respond 
        completion = openai.chat.completions.create( 
            model="gpt-4o-mini",
            messages=messages
        )
        return completion.choices[0].message.content
    except Exception as e:
        logging.exception("API Error")
        return "I'm having trouble responding right now. Please try again later."

@app.post("/twiml")
async def twiml_endpoint():
    """Endpoint that returns TwiML for Twilio to connect to the WebSocket"""
    xml_response = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
      <Connect>
        <ConversationRelay url="{WS_URL}" welcomeGreeting="{WELCOME_GREETING}" />
      </Connect>
    </Response>"""
    
    return Response(content=xml_response, media_type="text/xml")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    call_sid = None
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "setup":
                call_sid = message["callSid"]
                print(f"Setup for call: {call_sid}")
                websocket.call_sid = call_sid
                sessions[call_sid] = [{"role": "system", "content": SYSTEM_PROMPT}]
                
            elif message["type"] == "prompt":
                print(f"Processing prompt: {message['voicePrompt']}")
                conversation = sessions[websocket.call_sid]
                conversation.append({"role": "user", "content": message["voicePrompt"]})
                
                response = await ai_response(conversation)
                conversation.append({"role": "assistant", "content": response})
                
                await websocket.send_text(
                    json.dumps({
                        "type": "text",
                        "token": response,
                        "last": True
                    })
                )
                logging.info(f"Sent response: {response}")
                
            elif message["type"] == "interrupt":
                logging.info("Handling interruption.")
                
            else:
                logging.error(f"Unknown message type received: {message['type']}")
                logging.info("Please Try again")
                
    except WebSocketDisconnect:
        print("WebSocket connection closed")
        if call_sid:
            sessions.pop(call_sid, None)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
    logging.info(f"Server running at http://localhost:{PORT} and {WS_URL}")
