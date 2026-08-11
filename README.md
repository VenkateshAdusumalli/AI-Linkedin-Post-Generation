<<<<<<< HEAD
# AI-Linkedin-Post-Generation
=======
# AI LinkedIn Content Agent

A beginner-friendly pipeline that:

1. Checks a YouTube channel
2. Finds the latest video
3. Extracts the transcript in memory
4. Sends the transcript to Gemini
5. Prints a LinkedIn post for review

## Project structure

```text
ai-linkedin-agent/
├── agents/
│   ├── __init__.py
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
├── requirements.txt
└── sample check.py
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
```

## Run

```bash
python main.py
```

## Notes

- The transcript stays in memory; it is not saved to a file.
- This project intentionally keeps the architecture simple.
- No publishing, scheduling, image generation, or deployment features are included yet.
>>>>>>> b1e621c (Initial project setup)
