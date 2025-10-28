import os
from dotenv import load_dotenv
from openai import OpenAI
from fastapi import FastAPI, File, Form, UploadFile, BackgroundTasks, HTTPException
import asyncio
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import base64
import os
# import requests
# import msal
import smtplib
from email.message import EmailMessage

# load API Key and other secrets
load_dotenv()
# OpenAI
my_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=my_api_key)

# Email / SMTP settings (optional)
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Microsoft Graph / Teams (Client Credential flow)
MS_TENANT_ID = os.getenv("AZURE_TENANT_ID")
MS_CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
MS_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")
# Optional default target team/channel (you can override per request in the prompt)
DEFAULT_TEAM_ID = os.getenv("TEAMS_DEFAULT_TEAM_ID")
DEFAULT_CHANNEL_ID = os.getenv("TEAMS_DEFAULT_CHANNEL_ID")

# Class Chat Request 
class ChatRequest(BaseModel):
    prompt: str

# Class Chat Response
class ChatResponse(BaseModel):
    response: str

app = FastAPI()

# Add CORS middleware to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.post("/")
async def ai_prompt(request: ChatRequest, background_tasks: BackgroundTasks):
    """Main chat endpoint. If user asks to send an email or Teams message,
    schedule a background task to send it and return a confirmation along with the AI response.
    """
    # Call OpenAI as before
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "OpsInsight assistant."},
            {"role": "user", "content": request.prompt}
        ]
    )
    gpt_response = completion.choices[0].message.content

    # Simple intent detection (can be replaced with a more robust parser)
    text = request.prompt.lower()
    if "send email" in text or "send an email" in text:
        # Expectation: environment SMTP_* set OR user configured SendGrid — here we use SMTP
        if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
            raise HTTPException(status_code=400, detail="SMTP not configured (set SMTP_HOST/SMTP_USER/SMTP_PASSWORD)")
        # Very basic extraction: look for 'to <email>' and message after ':' or 'message'
        # This is a simple heuristic; consider a structured UI for production.
        to_addr = None
        body = None
        # find 'to ' followed by token with @
        import re
        m = re.search(r"to\s+([\w.@+-]+)", request.prompt, re.IGNORECASE)
        if m:
            to_addr = m.group(1)
        # Try to find quoted message or after 'message:'
        m2 = re.search(r"message\s*[:|-]\s*(.+)$", request.prompt, re.IGNORECASE)
        if m2:
            body = m2.group(1)
        if not to_addr:
            raise HTTPException(status_code=400, detail="Could not extract recipient email from prompt. Use 'send email to <email> message: <text>'.")
        if not body:
            # fallback to AI generated response as email body
            body = gpt_response

        background_tasks.add_task(send_email_smtp, to_addr, f"Message from OpsInsight assistant", body)

    if "send teams" in text or "post to team" in text or "send to team" in text:
        # Use Graph API client credentials to post into a channel (team + channel id required)
        if not MS_CLIENT_ID or not MS_CLIENT_SECRET or not MS_TENANT_ID:
            raise HTTPException(status_code=400, detail="Azure AD app not configured (set AZURE_CLIENT_ID/AZURE_CLIENT_SECRET/AZURE_TENANT_ID)")
        # Get target team/channel from prompt or fall back to DEFAULT_TEAM_ID/DEFAULT_CHANNEL_ID
        team_id = DEFAULT_TEAM_ID
        channel_id = DEFAULT_CHANNEL_ID
        # optional: extract team/channel from prompt (very basic)
        m = re.search(r"team\s+([0-9a-fA-F\-]{10,})", request.prompt)
        if m:
            team_id = m.group(1)
        m2 = re.search(r"channel\s+([0-9a-fA-F\-]{10,})", request.prompt)
        if m2:
            channel_id = m2.group(1)
        if not team_id or not channel_id:
            raise HTTPException(status_code=400, detail="Teams target not configured. Set TEAMS_DEFAULT_TEAM_ID and TEAMS_DEFAULT_CHANNEL_ID or mention team/channel ids in the prompt.")

        # content for Teams: try to extract after 'message:' or use AI response
        import re as _re
        m3 = _re.search(r"message\s*[:|-]\s*(.+)$", request.prompt, _re.IGNORECASE)
        message_text = m3.group(1) if m3 else gpt_response

        background_tasks.add_task(send_teams_message_graph, team_id, channel_id, message_text)

    return ChatResponse(response=gpt_response)
    


@app.post("/uploadfile/")
async def create_upload_file(
    prompt: str = Form(...),
    file : UploadFile = File(None)
):
    base64_image = None
    completion = None
    if file :
        content = await file.read()
        base64_image = base64.b64encode(content).decode("utf-8")

        completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}}
                    ]
                }
            ]
        )
    else :
            completion = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "OpsInsight assistant."},
                {"role": "user", "content": prompt}
            ]
            )

    if (completion):
        gpt_response = completion.choices[0].message.content
        return ChatResponse(response=gpt_response)
    return {"message": "No response"}


def get_graph_token():
    """Obtain an app-only token for Microsoft Graph using MSAL client credentials."""
    authority = f"https://login.microsoftonline.com/{MS_TENANT_ID}"
    app = msal.ConfidentialClientApplication(MS_CLIENT_ID, authority=authority, client_credential=MS_CLIENT_SECRET)
    token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])  # uses app permissions granted in Azure
    if "access_token" not in token:
        raise Exception(f"Could not acquire token: {token}")
    return token["access_token"]


def send_teams_message_graph(team_id: str, channel_id: str, content: str):
    """Send a message to a Teams channel using Microsoft Graph (app-only).
    Requires the Azure AD app to have the application permission 'ChannelMessage.Send' (admin consented).
    """
    try:
        access_token = get_graph_token()
        url = f"https://graph.microsoft.com/v1.0/teams/{team_id}/channels/{channel_id}/messages"
        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
        payload = {
            "body": {"contentType": "html", "content": content}
        }
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except Exception as e:
        # For now, print — in production use structured logging and retries
        print(f"Error sending Teams message: {e}")


def send_email_smtp(to_address: str, subject: str, body: str):
    """Send email via SMTP (basic TLS)."""
    try:
        msg = EmailMessage()
        msg["From"] = SMTP_USER
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        print(f"Error sending email: {e}")
