# AI LinkedIn Content Agent

A beginner-friendly pipeline that:

1. Checks a YouTube channel
2. Finds the latest video
3. Extracts the transcript in memory
4. Sends the transcript to Gemini
5. Generates a LinkedIn post
6. Generates an image prompt from the LinkedIn post
7. Sends the prompt to Cloudflare Workers AI
8. Saves a temporary image for review

## Project structure

```text
ai-linkedin-agent/
├── agents/
│   ├── __init__.py
│   ├── image_agent.py
│   └── linkedin_agent.py
├── config/
│   ├── __init__.py
│   └── settings.py
├── youtube/
│   ├── __init__.py
│   ├── transcript.py
│   └── youtube_client.py
├── .env
├── .gitignore
├── main.py
├── README.md
└── requirements.txt
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configure environment

Edit `.env` and add your real keys:

```env
YOUTUBE_API_KEY=your_youtube_key
GEMINI_API_KEY=your_gemini_key
YOUTUBE_CHANNEL_ID=UClXAalunTPaX1YV185DWUeg
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_api_token
```

## Run

```bash
python main.py
```

## Notes

- The transcript stays in memory and is passed directly to Gemini.
- The LinkedIn post is used to generate a relevant image prompt.
- Cloudflare Workers AI returns a Base64 image that is saved temporarily.
- No LinkedIn publishing or permanent image archiving is implemented yet.
