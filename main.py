import html
import os
import re
import edge_tts
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
import google.generativeai as genai
from pydantic import BaseModel

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

app = FastAPI(title="Movie Recap Generator API")


class AudioRequest(BaseModel):
    script_text: str
    output_file: str = "recap_voiceover.mp3"


@app.get("/api/search-movie")
def search_movie(title: str):
    import requests

    if not TMDB_API_KEY:
        raise HTTPException(status_code=500, detail="TMDB API Key မရှိပါ။")

    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={title}"
    response = requests.get(url)

    if response.status_code != 200:
        raise HTTPException(
            status_code=500, detail="TMDB မှ ဒေတာ ဆွဲယူ၍ မရပါ။"
        )

    return response.json()


@app.post("/api/generate-script")
def generate_script(
    title: str, duration_seconds: int = 60, language: str = "Burmese"
):
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API Key မရှိပါ။")

    # Gemini ထံမှ Voiceover စာသားသန့်သန့်ပဲ ထွက်လာစေရန် အမိန့်ပေးထားပါသည်
    prompt = f"""
    You are a professional movie recap narrator. 
    Write ONLY the spoken narration/voiceover script for the movie '{title}' in {language}.
    Target Video Duration: {duration_seconds} seconds.

    STRICT RULES:
    - Do NOT include any visual cues, camera directions, or timestamps.
    - Do NOT use brackets [ ], parentheses ( ), or curly braces {{ }}.
    - Do NOT write English titles, headers, or bullet points.
    - Output ONLY pure, printable Burmese sentences for direct speech synthesis.
    """

    model = genai.GenerativeModel("gemini-3.5-flash")
    response = model.generate_content(prompt)

    return {"script": response.text}


@app.post("/api/generate-audio")
async def generate_audio(request: AudioRequest):
    try:
        raw_text = request.script_text

        # 1. HTML Entities & Quotes ရှင်းခြင်း
        clean_text = html.unescape(raw_text)
        clean_text = clean_text.replace('"', "").replace("'", "")

        # 2. Bracket မည်သည့် အမျိုးအစားမဆို [..], (...), {..} ထဲက စာလုံးများ အကုန်ဖျက်ခြင်း
        clean_text = re.sub(r"\[.*?\]", "", clean_text)
        clean_text = re.sub(r"\(.*?\)", "", clean_text)
        clean_text = re.sub(r"\{.*?\}", "", clean_text)

        # 3. English ခေါင်းစဉ်များ၊ Label စာကြောင်းများ (ဥပမာ Narration:, Visual:) ဖျက်ခြင်း
        clean_text = re.sub(
            r"^[A-Za-z0-9\s_]+:\s*", "", clean_text, flags=re.MULTILINE
        )

        # 4. Markdown သင်္ကေတများ (*, #, -, _, ~) ဖျက်ခြင်း
        clean_text = re.sub(r"[\*#\-_~]+", " ", clean_text)

        # 5. \n စာကြောင်းအဆက်များနှင့် ပိုနေသော ကွက်လပ်များ ဖျက်ခြင်း
        clean_text = (
            clean_text.replace("\\n", " ").replace("\n", " ").replace("#", "")
        )
        clean_text = re.sub(r"\s+", " ", clean_text).strip()

        if not clean_text:
            raise HTTPException(
                status_code=400, detail="ဖတ်ရှုရမည့် စာသား သန့်သန့် မရှိပါ။"
            )

        # Edge-TTS သို့ စာသားသန့်သန့် ပေးပို့ခြင်း
        communicate = edge_tts.Communicate(clean_text, "my-MM-NilarNeural")
        await communicate.save(request.output_file)

        return {
            "status": "success",
            "audio_file": request.output_file,
            "cleaned_text": clean_text,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"အသံဖိုင် ထုတ်လုပ်ရာတွင် Error တက်သွားသည်: {str(e)}",
        )