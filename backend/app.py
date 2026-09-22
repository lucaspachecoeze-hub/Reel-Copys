import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import yt_dlp
from openai import OpenAI

load_dotenv()

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

app = FastAPI(title="Reel Copy Generator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class GenerateRequest(BaseModel):
    url: str
    tone: str = "casual y directo"


class GenerateResponse(BaseModel):
    transcript: str
    copy: str


MAX_AUDIO_BYTES = 24 * 1024 * 1024  # stay under Whisper's 25MB limit


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    if not GROQ_API_KEY:
        raise HTTPException(500, "Falta GROQ_API_KEY en el servidor.")

    client = OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = Path(tmpdir) / "audio.mp3"
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(Path(tmpdir) / "audio.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }],
            "quiet": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([req.url])
        except Exception as e:
            raise HTTPException(400, f"No pude descargar el video de ese link: {e}")

        if not audio_path.exists():
            raise HTTPException(400, "No se pudo extraer audio de ese link.")

        if audio_path.stat().st_size > MAX_AUDIO_BYTES:
            raise HTTPException(400, "El audio es demasiado largo (límite ~25MB, unos 20-25 min).")

        with open(audio_path, "rb") as f:
            transcript_resp = client.audio.transcriptions.create(
                model="whisper-large-v3",
                file=f,
            )
        transcript = transcript_resp.text.strip()

    if not transcript:
        raise HTTPException(400, "La transcripción salió vacía.")

    prompt = f"""Sos copywriter especializado en Instagram Reels. Te paso la transcripción de un video. \
Escribí una descripción (copy) lista para publicar en Instagram, en tono {req.tone}.

Reglas:
- Primera línea que enganche (hook), sin spoilear todo el video.
- Cuerpo corto, párrafos cortos, fácil de leer en el feed.
- Incluí 3-6 hashtags relevantes al final.
- No inventes datos que no estén en la transcripción.
- Devolvé SOLO el copy final, sin explicaciones ni comillas envolventes.

Transcripción:
\"\"\"{transcript}\"\"\"
"""
    chat_resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=800,
    )
    copy_text = chat_resp.choices[0].message.content.strip()

    return GenerateResponse(transcript=transcript, copy=copy_text)
