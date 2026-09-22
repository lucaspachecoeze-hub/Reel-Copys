import os
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
MAX_UPLOAD_BYTES = 300 * 1024 * 1024  # raw video upload cap


def get_client() -> OpenAI:
    if not GROQ_API_KEY:
        raise HTTPException(500, "Falta GROQ_API_KEY en el servidor.")
    return OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)


def transcribe(client: OpenAI, audio_path: Path) -> str:
    if not audio_path.exists():
        raise HTTPException(400, "No se pudo extraer audio de ese video.")
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
    return transcript


def generate_copy(client: OpenAI, transcript: str, tone: str) -> str:
    prompt = f"""Sos copywriter especializado en Instagram Reels. Te paso la transcripción de un video. \
Escribí una descripción (copy) lista para publicar en Instagram, en tono {tone}.

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
    return chat_resp.choices[0].message.content.strip()


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    client = get_client()

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

        transcript = transcribe(client, audio_path)

    copy_text = generate_copy(client, transcript, req.tone)
    return GenerateResponse(transcript=transcript, copy=copy_text)


@app.post("/api/generate-upload", response_model=GenerateResponse)
async def generate_upload(file: UploadFile = File(...), tone: str = Form("casual y directo")):
    client = get_client()

    with tempfile.TemporaryDirectory() as tmpdir:
        suffix = Path(file.filename or "video").suffix or ".mp4"
        video_path = Path(tmpdir) / f"input{suffix}"
        audio_path = Path(tmpdir) / "audio.mp3"

        size = 0
        with open(video_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(400, "El archivo es demasiado grande (límite 300MB).")
                out.write(chunk)

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(video_path), "-vn", "-acodec", "libmp3lame",
                 "-q:a", "4", str(audio_path)],
                check=True, capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise HTTPException(400, f"No pude extraer el audio del archivo: {e.stderr.decode(errors='ignore')[:300]}")

        transcript = transcribe(client, audio_path)

    copy_text = generate_copy(client, transcript, tone)
    return GenerateResponse(transcript=transcript, copy=copy_text)
