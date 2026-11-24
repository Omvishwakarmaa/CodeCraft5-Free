# CodeCraft 5 — Zero-cost build

This version does not call OpenAI API, ElevenLabs, or any paid AI service.
No API key or API billing is needed.

## Features
- Local rule-based knowledge base for basic programming/web topics
- Hindi/English/Hinglish-friendly answers where matching rules exist
- Fixed fallback response for unknown questions
- Browser speech input (SpeechRecognition, if supported by browser)
- Browser text-to-speech playback on the Listen button
- Thunder / Water animated themes with short generated sound effects
- Light / dark mode
- SQLite chat history
- Flask + Gunicorn deployment support

## Run on Mac
From this folder in VS Code Terminal:
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python chatbot.py
```
Open http://127.0.0.1:5002

## Render
Build command: `pip install -r requirements.txt`
Start command: `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT chatbot:app`
Set `SECRET_KEY` to a long random value. For persistent SQLite history, attach a Render disk and set `DATA_DIR` to its mount path.

## Important limitations
- This is a local rule-based knowledge base, not a generative AI model. Unknown questions get the configured fallback reply.
- Mic input uses the browser Web Speech API. Use Google Chrome on the same Mac and open http://127.0.0.1:5002 (localhost is a secure context). Allow microphone permission when prompted. Safari may not expose SpeechRecognition; if so, use Chrome or macOS Dictation. Speech recognition may use browser/platform speech services and may require internet; it is not guaranteed offline.
- Speech output uses the browser's installed voices. It is not a clone of Om's voice.
- Image understanding is intentionally not included in this zero-cost build.
- No OpenAI API key, OpenAI API billing, or voice-cloning subscription is required.

## Logo
The supplied CodeCraft 5 logo is installed at `static/codecraft5-logo.jpg` and is used in the header and browser favicon.

## Developer links
The UI footer credits Om Vishwakarma and links to Instagram (omzyric) and LinkedIn (omvishwakarmaa).

## Expanded B.Tech CSE knowledge base
Includes curated offline answers for programming fundamentals, Python, OOP, C pointers,
data structures and algorithms, operating systems, DBMS, networking, web basics,
cybersecurity, cloud computing, AI and machine learning. Add or edit entries in
`reply_for()` in `chatbot.py`. Unknown topics still return the configured fallback.
