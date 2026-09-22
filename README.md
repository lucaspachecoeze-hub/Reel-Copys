# Reel Copy Generator

Pegás el link de un video (Google Drive, YouTube, o cualquier link directo), lo transcribe, y genera un copy listo para publicar en Instagram.

Stack 100% gratuito: FastAPI + yt-dlp + Groq (Whisper para transcribir, Llama para el copy), desplegado en el free tier de Render.

## 1. Conseguir la API key gratis de Groq

1. Andá a https://console.groq.com y creá una cuenta (no pide tarjeta).
2. En el menú lateral, entrá a **API Keys** → **Create API Key**.
3. Copiá la key (empieza con `gsk_...`) y guardala.

## 2. Probarlo localmente (opcional)

Necesitás `ffmpeg` instalado (`brew install ffmpeg` en Mac).

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # y pegá tu GROQ_API_KEY ahí
uvicorn app:app --reload
```

Abrí http://localhost:8000

## 3. Subir el proyecto a GitHub

```bash
cd reel-copy-app
git init
git add .
git commit -m "Initial commit"
```

Creá un repo nuevo en https://github.com/new (público o privado) y seguí las instrucciones para pushear (`git remote add origin ...` y `git push`).

## 4. Desplegar gratis en Render

1. Andá a https://render.com y creá una cuenta (podés entrar con GitHub).
2. **New +** → **Blueprint** → conectá tu repo de GitHub.
3. Render va a detectar el archivo `render.yaml` y va a pedir el valor de `GROQ_API_KEY` — pegá la key del paso 1.
4. Dale **Apply**. El primer deploy tarda unos minutos.
5. Cuando termine, te da una URL tipo `https://reel-copy-app.onrender.com` — esa es tu app.

**Nota sobre el free tier de Render:** el servicio se "duerme" tras ~15 min sin uso, así que la primera request después de un rato de inactividad puede tardar ~30-50 segundos en levantar. Para uso personal ocasional no es un problema.

## Límites

- Videos de hasta ~20-25 minutos (límite de tamaño de audio de la API de transcripción).
- El link de Drive tiene que estar compartido como "cualquiera con el link" para que se pueda descargar.
