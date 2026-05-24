## Google
### Official Google Workspace MCPs (not completed)
- https://developers.google.com/workspace/guides/configure-mcp-servers

### Official Google Cloud MCPs
- https://developers.google.com/workspace/guides/configure-mcp-servers


## High value MCP integrations for a personal organiser

### Communication

| Tool | MCP available? | Use case |
| :--- | :--- | :--- |
| WhatsApp | Community servers exist | Message people directly |
| Slack | Official MCP | Work comms, send/search messages |
| Telegram itself | Via Bot API | Send to other chats, channels |

### Notes & Knowledge

| Tool | MCP available? | Use case | 
| :--- | :--- | :--- |
| Notion | Official | MCPNotes, databases, project pages |
| Obsidian | Community MCP | Personal knowledge base | 
| Google Keep | No official MCP yet | Quick notes |

### Tasks & Projects

| Tool | MCP available? | Use case |
| :--- | :--- | :--- |
| Todoist | Official MCP | Richer task management than Google Tasks |
| Trello | Official MCP | Board-based project tracking | 
| Linear | Official MCP | Dev-focused issue tracking | 
| Asana | Official MCP | Team project management | 
| Jira | Official MCP | Dev tickets |

### Finance & Life

| Tool | MCP available? | Use case | 
| :--- | :--- | :--- |
| Stripe | Official MCP | Invoice status, payment tracking | 
| GitHub | Official MC | PPR status, issues, commits | 
| Weather | Multiple MCP servers | "Do I need an umbrella Thursday?" |
| Google Maps | Official GCP MCP | Travel time, directions | 
| Spotify | Community MCP | Play music by mood/context |

### Productivity

| Tool | MCP available? | Use case | 
| :--- | :--- | :--- |
| Browser/web search | Official pydantic-ai built-in | Research, lookup, current info |
| Browserbase / Playwright | Official MCP | Web automation, form filling | 
| PDF / document reading | Multiple MCP servers | Summarise attachments |


## Telegram Voice Messages
**What happens when you send a voice message on Telegram**
Telegram sends your bot an `Update` with a `voice` object instead of text. It contains a file_id you use to download the `.ogg` audio file from Telegram's servers.

What you need to add
* **1.** Download the voice file
Telegram Bot API has a getFile + download endpoint. One httpx call.
* **2.** Transcribe it Convert speech to text. The obvious choice is OpenAI Whisper  either:
  - openai-whisper — runs locally, free, but needs decent CPU/RAM on Render
  - OpenAI Whisper API — cloud, fast, costs ~$0.006/min, trivial to call

For Render deployment, the API is the better call — local Whisper is heavy.
* **3.** Feed the transcript into your existing agent loop
The transcript becomes the text variable in your webhook handler. Everything downstream is identical — SupervisorAgent.run(transcript, deps). Zero changes to agents.

Code changes — only in gateway/app.py
```python
async def transcribe_voice(file_id: str) -> str:
    """Download voice from Telegram and transcribe via Whisper API."""
    # 1. Get file path from Telegram
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{_BASE}/getFile",
            params={"file_id": file_id}
        )
    file_path = r.json()["result"]["file_path"]

    # 2. Download the .ogg file
    async with httpx.AsyncClient() as client:
        audio = await client.get(
            f"https://api.telegram.org/file/bot{_TOKEN}/{file_path}"
        )

    # 3. Transcribe via Whisper API
    from openai import AsyncOpenAI
    oai = AsyncOpenAI()
    transcript = await oai.audio.transcriptions.create(
        model="whisper-1",
        file=("voice.ogg", audio.content, "audio/ogg"),
    )
    return transcript.text
```

Then in your webhook handler, add alongside the text check:
```python
# existing
text = message.get("text", "").strip()

# add this
if not text and message.get("voice"):
    file_id = message["voice"]["file_id"]
    text = await transcribe_voice(file_id)
    logger.info("webhook | voice transcribed | text=%r", text)
```