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
        
        # config: { speed: number, voice: ..., companion: 'dog'|'bird'|... }
        config = data.get('config', {}) 
        voice_type = config.get('voice', 'female')
        companion = config.get('companion', 'dog') # Default to dog

        print(f"[{place_name}] Request: {mode} / Voice: {voice_type} / Companion: {companion} / Lang: {lang}")

        # --- Voice Settings (Pitch & Rate) ---
        # Default settings
        voice_name = "ja-JP-NanamiNeural" if lang == 'ja' else "en-US-AvaNeural"
        voice_pitch = "+0Hz"
        voice_rate = "+0%"
        
        # Adjust voice settings based on Companion TYPE
        if companion == 'dog':
            # Dog: Energetic (Little high pitch)
            voice_rate = "+10%"
            voice_pitch = "+5Hz"
        elif companion == 'bird':
            # Owl: Wise (Little slow)
            voice_rate = "-5%"
            voice_pitch = "-5Hz"
        elif companion == 'monkey':
            # Monkey: Fast and High
            voice_rate = "+15%"
            voice_pitch = "+15Hz"
        elif companion == 'bear':
            # Bear: Deep and Slow
            voice_name = "ja-JP-KeitaNeural" # Male voice for bear
            voice_rate = "-10%"
            voice_pitch = "-15Hz"
        elif companion == 'horse':
            # Horse: Noble (Standard/Elegant)
            voice_rate = "0%"
            voice_pitch = "-5Hz"

        # --- Prompt Construction (Persona Based) ---
        
        # Define persona instructions
        persona_instruction = ""
        if lang == 'ja':
            if companion == 'dog':
                persona_instruction = "あなたの正体は「忠実な柴犬」です。語尾に「ワン！」や「だワン」をつけて、元気に案内してください。「ご主人様」と呼びかけてください。"
            elif companion == 'bird':
                persona_instruction = "あなたの正体は「物知りなフクロウ」です。語尾に「ホ」や「ですので」をつけて、博士のように落ち着いて解説してください。"
            elif companion == 'monkey':
                persona_instruction = "あなたの正体は「いたずら好きのサル」です。語尾に「ウッキー」や「だキー」をつけて、ハイテンションで案内してください。"
            elif companion == 'bear':
                persona_instruction = "あなたの正体は「優しいクマ」です。語尾に「クマ」をつけて、のんびりと優しく案内してください。「～だなぁ」という口調が特徴です。"
            elif companion == 'horse':
                persona_instruction = "あなたの正体は「高貴な馬」です。語尾に「ヒヒーン」はつけすぎず、丁寧語で「～でございます」と執事のように案内してください。"
        else:
            # Simple English fallbacks
             persona_instruction = f"You are a {companion}. Speak with the personality of a {companion}."

        if mode == 'simple':
            # Simple Mode
            if lang == 'ja':
                prompt = f"""
                あなたは旅行者の相棒（{companion}）として、現在地「{place_name}」の面白いトリビアを2〜3文で教えてください。
                
                【役割設定】
                {persona_instruction}
                
                【必須・構成】
                ・**書き出しは「{place_name}だ{('ワン' if companion=='dog' else '')}！」のように、場所の名前を呼ぶことから始めてください。**
                ・その場所が何なのか簡潔に教え、その後に「実は...」と意外な情報を一つ教えてください。
                
                [元データ]
                {wiki_text[:1000]}
                """
            else:
                 prompt = f"""
                Acting as a travel companion ({companion}), tell the user about "{place_name}" in 2-3 sentences.
                {persona_instruction}
                Start by introducing the place name.
                
                [Source]
                {wiki_text[:1000]}
                """
        else:
            # Detail Mode
            if lang == 'ja':
                prompt = f"""
                あなたは旅行者の相棒（{companion}）として、現在地「{place_name}」について詳しく（400文字程度）ガイドしてください。
                
                【役割設定】
                {persona_instruction}

                【構成】
                1. 挨拶と場所の紹介
                2. 歴史や背景（元データに基づく）
                3. 見どころや豆知識
                4. 締めの言葉（次の冒険へ促す）

                [元データ]
                {wiki_text[:2000]}
                """
            else:
                 prompt = f"""
                Acting as a travel companion ({companion}), explain "{place_name}" in detail (approx 150 words).
                {persona_instruction}
                
                [Source]
                {wiki_text[:2000]}
                """

        # --- Generate Text ---
        response = model.generate_content(prompt)
        guide_script = response.text
        
        # --- Generate Audio (edge-tts) ---
        # 非同期関数を同期的に実行するためのヘルパー
        async def synthesize_text(text, voice, pitch, rate):
            # edge-tts set pitch/rate via communicate object
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
