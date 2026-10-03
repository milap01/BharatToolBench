"""Lists the models YOUR API keys can use. No SDK needed (standard library only).

Mac/Linux:
  export OPENAI_API_KEY="..."      export GEMINI_API_KEY="..."
  python3 check_models.py
Windows (PowerShell):
  $env:OPENAI_API_KEY="..."        $env:GEMINI_API_KEY="..."
Never paste keys into chat, code files, or git.
"""
import json
import os
import urllib.error
import urllib.request


def get(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def show(title, names):
    print(f"\n=== {title} ({len(names)} found) ===")
    for n in sorted(names):
        print("  ", n)


def main():
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        print("OPENAI_API_KEY not set - skipping OpenAI")
    else:
        try:
            d = get("https://api.openai.com/v1/models", {"Authorization": f"Bearer {k}"})
            ids = [m["id"] for m in d.get("data", [])]
            # keep text/chat-style models, hide embeddings/audio/image/etc.
            skip = ("embed", "whisper", "tts", "dall-e", "image", "audio", "realtime",
                    "moderation", "transcribe", "sora", "search")
            show("OpenAI", [i for i in ids if i.startswith(("gpt", "o")) and not any(s in i for s in skip)])
        except urllib.error.HTTPError as e:
            print("OpenAI error:", e.code, e.read()[:300])
        except Exception as e:
            print("OpenAI error:", e)

    k = os.environ.get("GEMINI_API_KEY")
    if not k:
        print("GEMINI_API_KEY not set - skipping Gemini")
    else:
        try:
            d = get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
                    {"x-goog-api-key": k})
            names = [m["name"].split("/")[-1] for m in d.get("models", [])
                     if "generateContent" in m.get("supportedGenerationMethods", [])
                     and "gemini" in m["name"]]
            show("Gemini (supports generateContent)", names)
        except urllib.error.HTTPError as e:
            print("Gemini error:", e.code, e.read()[:300])
        except Exception as e:
            print("Gemini error:", e)


if __name__ == "__main__":
    main()
