import os
import asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
import edge_tts
import io
import base64
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# ==========================================
# ★ここにAPIキーを貼り付け
# ==========================================
# .envファイルから読み込みます
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('models/gemini-flash-latest')

# 1. サイト表示（地図＆スポットリスト）
@app.route('/')
def home():
    return render_template('google_map_app.html', google_api_key=GOOGLE_API_KEY)

# 2. ガイド生成（Wikiテキストを受け取ってGeminiで要約・音声化）
@app.route('/generate_guide', methods=['POST'])
def generate_guide():
    try:
        data = request.json
        wiki_text = data.get('text', '')
        place_name = data.get('title', 'This place')
        lang = data.get('lang', 'ja')
        mode = data.get('mode', 'detail') # simple/detail
        # config: { speed: number, voice: 'female'|'male'|'tsuda'|'kitty' }
        config = data.get('config', {}) 
        voice_type = config.get('voice', 'female')

        print(f"[{place_name}] Request: {mode} / Voice: {voice_type} / Lang: {lang}")

        # --- Voice Settings (Pitch & Rate only) ---
        # Default settings (Female)
        voice_name = "ja-JP-NanamiNeural" if lang == 'ja' else "en-US-AvaNeural"
        voice_pitch = "+0Hz"
        voice_rate = "+0%"
        
        if voice_type == 'male':
            voice_name = "ja-JP-KeitaNeural" if lang == 'ja' else "en-US-AndrewNeural"
        
        elif voice_type == 'tsuda':
            # 津田健次郎風 (渋い男性)
            # 低音でゆっくり話すことで落ち着きと深みを表現
            voice_name = "ja-JP-KeitaNeural" if lang == 'ja' else "en-US-BrianNeural"
            voice_pitch = "-12Hz" 
            voice_rate = "-5%"

        elif voice_type == 'kitty':
            # ハローキティ風 (元気な女性)
            # ピッチを上げて少し早口にすることで明るさを表現
            voice_name = "ja-JP-NanamiNeural" if lang == 'ja' else "en-US-AnaNeural"
            voice_pitch = "+20Hz"
            voice_rate = "+5%"
            
        elif voice_type == 'kyoko':
            # 齊藤京子風 (低音ボイスのアイドル)
            # Nanamiをベースにピッチを下げてハスキーさを表現
            voice_name = "ja-JP-NanamiNeural" if lang == 'ja' else "en-US-AvaNeural"
            voice_pitch = "-10Hz"
            voice_rate = "-2%"

        # --- Prompt Construction (UNIFIED) ---
        # キャラクターごとの口調指示は廃止し、常に「公式ガイド風」を使用
        
        if mode == 'simple':
            # Simple Mode Prompt (Trivia/Context focused)
            if lang == 'ja':
                prompt = f"""
                観光スポット「{place_name}」に今まさに立っている旅行者に向けて、その場所の「最も面白いトリビア」や「意外な歴史」を2〜3文（100〜140文字）で教えてください。
                
                【必須・構成】
                ・**必ず「{place_name}は、...」という書き出しで始めてください。**（「ここは」や「この場所は」は禁止）
                ・まず、そこが何なのか（寺、公園など）を簡潔に言い、その後に「実は...」と意外な事実を続けてください。
                
                【禁止】「赤い建物です」等の見た目の描写（見ればわかるため）。
                
                [元データ]
                {wiki_text[:1000]}
                """
            else:
                prompt = f"""
                Tell a traveler standing at "{place_name}" the most interesting trivia or hidden history in 2-3 sentences (40-60 words).
                
                [Requirements]
                - **MUST start with "{place_name} is..."**. (Do not use "Here is" or "This place is")
                - First, briefly state what it is, then follow with "Actually..." to share a hidden fact.
                
                [Prohibited] Visual descriptions.
                
                [Source]
                {wiki_text[:1000]}
                """

        else:
            # Detail Mode Prompt (Deep dive with gentle intro)
            if lang == 'ja':
                prompt = f"""
                あなたは現地にいる旅行者にその場所の深い魅力を伝えるプロのガイドです。「{place_name}」について解説してください。

                【構成指示】
                1. **導入 (10秒程度)**: まず、「{place_name}は...」という主語で始め、ここが何なのか（寺なのか、公園なのか等）を優しく完結に説明してください。「ここは」等の代名詞は避けてください。
                2. **本題**: その後、「実は...」と切り出し、歴史的背景や隠されたエピソード、意外なトリビアを深く語ってください。
                3. **締め**: 滞在が楽しくなるような言葉で締めてください。

                【禁止事項】
                ・「目の前にあるものの詳細な見た目説明」（見ればわかるため）。
                ・「住所の説明」（既に現地にいるため）。

                【制約】
                ・文字数は「400文字程度（読み上げ約1分）」
                
                [元データ] {wiki_text[:5000]}
                """
            else:
                prompt = f"""
                You are a professional guide explaining "{place_name}" to a traveler currently at the spot.

                [Structure]
                1. **Intro (approx 10s)**: Start with "{place_name} is...", gently and briefly explaining what this place is. Do not use generic pronouns like "Here is...".
                2. **Deep Dive**: Then, transition with "Actually..." or "Historically..." to share hidden facts, deep history, and trivia.
                3. **Conclusion**: End with a welcoming closing.

                [Strict Prohibitions]
                - Visual descriptions of obvious things.
                - Address/Location explanations.

                [Constraints]
                - Approx 150 words (1 min speech).
                
                [Source] {wiki_text[:5000]}
                """

        # --- Generate Text ---
        response = model.generate_content(prompt)
        guide_script = response.text
        
        # --- Generate Audio (edge-tts) ---
        # 非同期関数を同期的に実行するためのヘルパー
        async def synthesize_text(text, voice, pitch, rate):
            # edge-tts set pitch/rate via communicate object
            # Note: edge-tts API usually takes options in the text string or args, 
            # but for simple pitch/rate, we pass them as params if library supports, 
            # Or formatted as "+0Hz", "+0%" strings.
            communicate = edge_tts.Communicate(text, voice, pitch=pitch, rate=rate)
            out = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    out.write(chunk["data"])
            out.seek(0)
            return out

        # WindowsのFlask/asyncio相性問題回避
        mp3_fp = asyncio.run(synthesize_text(guide_script, voice_name, voice_pitch, voice_rate))
        
        mp3_base64 = base64.b64encode(mp3_fp.read()).decode('utf-8')
        audio_uri = f"data:audio/mp3;base64,{mp3_base64}"

        return jsonify({
            "script": guide_script,
            "audio_uri": audio_uri
        })

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Cloud environments (like Render) provide a PORT via env var
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
