import os, json, asyncio, feedparser, requests, edge_tts
from groq import Groq
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. Fetch Live News & Sports RSS (Cricket, Football, Volleyball, Headlines)
FEEDS = [
    "https://espncricinfo.com",
    "https://google.com",
    "https://google.com"
]

def get_latest_story():
    seen = open("seen.txt").read().splitlines() if os.path.exists("seen.txt") else []
    for url in FEEDS:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            if entry.link not in seen:
                with open("seen.txt", "a") as f:
                    f.write(entry.link + "\n")
                return entry.title, entry.get("summary", entry.title)
    return None, None

# 2. Generate 30-sec Script & 4 AI Image Prompts (Free Groq API)
def generate_script_and_prompts(title, summary):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    prompt = f"""Create a viral 30-second YouTube Short script (max 65 words) about this news/score:
Title: {title}
Details: {summary}

Return ONLY valid JSON with keys:
"yt_title": catchy title under 60 chars with #Shorts,
"script": energetic narration text only,
"image_prompts": list of 4 vivid, vertical 9:16 photo-realistic scene prompts (no text in images)."""
    
    res = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"}
    )
    return json.loads(res.choices[0].message.content)

# 3. Generate Free AI Images & Voiceover
async def build_assets(data):
    communicate = edge_tts.Communicate(data["script"], "en-IN-PrabhatNeural")
    await communicate.save("voice.mp3")
    
    img_paths = []
    for i, p in enumerate(data["image_prompts"][:4]):
        url = f"https://pollinations.ai{requests.utils.quote(p)}?width=1080&height=1920&nologo=true"
        img_data = requests.get(url, timeout=60).content
        path = f"img_{i}.jpg"
        with open(path, "wb") as f:
            f.write(img_data)
        img_paths.append(path)
    return img_paths

# 4. Assemble 1080x1920 Video
def render_video(img_paths):
    audio = AudioFileClip("voice.mp3")
    dur = audio.duration / len(img_paths)
    clips = [ImageClip(p).set_duration(dur).resize((1080, 1920)) for p in img_paths]
    video = concatenate_videoclips(clips, method="compose").set_audio(audio)
    video.write_videofile("short.mp4", fps=24, codec="libx264", audio_codec="aac")

# 5. Auto-Upload to YouTube
def upload_youtube(yt_title, script):
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://googleapis.com",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"]
    )
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": yt_title[:95],
            "description": f"{script}\n\n#Shorts #News #Cricket #Sports",
            "categoryId": "25"
        },
        "status": {"privacyStatus": "public"}
    }
    media = MediaFileUpload("short.mp4", chunksize=-1, resumable=True)
    youtube.videos().insert(part="snippet,status", body=body, media_body=media).execute()

if __name__ == "__main__":
    title, summary = get_latest_story()
    if title:
        data = generate_script_and_prompts(title, summary)
        imgs = asyncio.run(build_assets(data))
        render_video(imgs)
        upload_youtube(data["yt_title"], data["script"])
