import os
import io
import logging
import asyncio
from dotenv import load_dotenv

# FastAPI kutubxonalari (Ilova API yo'lagi uchun)
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Yangi rasmiy Google SDK (Gemini uchun)
from google import genai
from google.genai import types

# Video va Ovoz kutubxonalari
from moviepy import VideoFileClip
import whisper

# PDF kutubxonasi
import fitz  # PyMuPDF

# Telegram Bot API kutubxonalari
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# ==============================
# 1️⃣ SOZLAMALAR VA INITIALIZATION
# ==============================
load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

if not TOKEN:
    raise ValueError("XATOLIK: 'TELEGRAM_TOKEN' muhit o'zgaruvchisi topilmadi!")
if not GEMINI_KEY:
    raise ValueError("XATOLIK: 'GEMINI_API_KEY' muhit o'zgaruvchisi topilmadi!")

# Gemini klienti
client = genai.Client(api_key=GEMINI_KEY)

# Whisper modelini yuklab olamiz (Faqat fonda yuklanadi)
logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

print("⏳ Whisper modeli yuklanmoqda...")
whisper_model = whisper.load_model("base")
print("✅ Whisper modeli tayyor!")

# FastAPI veb-server obyekti
app = FastAPI(title="Universal AI Translator Platform API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Kiber-neon interfeys uchun tayyor HTML shablon matni
html_shablon = """
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <title>AI Multimodal Standalone App</title>
    <style>
        body { background-color: #0d1117; color: #39FF14; font-family: 'Segoe UI', sans-serif; text-align: center; padding: 50px; }
        .container { border: 2px solid #39FF14; display: inline-block; padding: 30px; border-radius: 10px; box-shadow: 0 0 15px #39FF14; }
        h1 { margin-bottom: 10px; }
        p { color: #888; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🟢 Universal AI Center</h1>
        <p>Tizim va Telegram Bot fonda muvaffaqiyatli ishlamoqda...</p>
    </div>
</body>
</html>
"""

# ==============================
# 2️⃣ START KOMANDASI VA TUGMALAR HANDLERI
# ==============================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    
    welcome_text = (
        f"👋 <b>Assalomu alaykum, {user_name}!</b>\n\n"
        f"🤖 Men — <b>Gemini 2.5</b> neyron tarmog'i negizida ishlovchi universal "
        f"<b>Ko'p tilli Tarjimon Asistentman</b>. Menga yuborilgan har qanday ma'lumotni zudlik bilan o'zbek tiliga o'girib beraman.\n\n"
        f"<b>📌 Tizim imkoniyatlari:</b>\n"
        f"📝 <b>Matnli tarjima:</b> Istalgan tildagi uzun matnlarni yuboring.\n"
        f"📄 <b>PDF Hujjatlar:</b> PDF elektron kitob yoki maqolalarni o'zbekcha tahlil qilaman.\n"
        f"🖼 <b>Tasvirlar (Vision):</b> Rasmdagi yozuvlarni o'zbekchaga o'giraman.\n"
        f"🎬 <b>Video tarjima:</b> 2 minutgacha bo'lgan videolarni ovozini eshitib tarjima qilaman!\n\n"
        f"<i>💡 To'g'ridan-to'g'ri biron bir matn, PDF, rasm yoki video yuborib sinab ko'ring!</i>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Matn tarjimasi", callback_data="help_translation"),
            InlineKeyboardButton("📄 PDF tahlili", callback_data="help_pdf")
        ],
        [
            InlineKeyboardButton("🖼 Rasm (Vision)", callback_data="help_vision"),
            InlineKeyboardButton("🎥Video tarjima uchun", callback_data="help_vision")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode="HTML")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_translation":
        await query.message.reply_text("📝 Matnni to'g'ridan-to'g'ri yuboring, avtomatik o'zbekchaga o'giriladi.")
    elif query.data == "help_pdf":
        await query.message.reply_text("📄 Chet tilidagi PDF kitobni fayl shaklida yuboring.")
    elif query.data == "help_vision":
        await query.message.reply_text("🖼 Yozuvi bor istalgan rasmni yuboring.")

# ==============================
# 3️⃣ PDF TAHLILI FUNKSIYASI
# ==============================
async def analyze_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document: return
    if not update.message.document.file_name.lower().endswith('.pdf'): return

    status_msg = await update.message.reply_text("PDF qabul qilindi. Matn o'qilmoqda... 📄")
    file = await update.message.document.get_file()

    try:
        pdf_bytes = await file.download_as_bytearray()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        full_text = "".join([page.get_text() for page in doc])
        doc.close()

        clean_text = full_text.strip()
        if len(clean_text) > 10:
            await status_msg.edit_text("Hujjat tahlil qilinmoqda... ✨")
            prompt = f"Ushbu kitob/matn mazmunini o'zbek tilida chiroyli tushuntirib ber, oxirida kimlar uchun foydaliligini yoz:\n\nMatn: {clean_text[:12000]}"
            
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            final_output = response.text.strip() if response.text else "Tahlil natijasi bo'sh."
            
            await status_msg.delete()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=final_output[:3500])
        else:
            await status_msg.edit_text("PDF ichida o'qish uchun matn topilmadi.")
    except Exception as e:
        logger.error(f"PDF xatosi: {e}")
        await status_msg.edit_text("PDF tahlilida xatolik yuz berdi.")

# ==============================
# 4️⃣ MULTIMODAL (RASM) FUNKSIYASI
# ==============================
async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        status_msg = await update.message.reply_text("Rasm o'qilmoqda va matn aniqlanmoqda... 🔍")
        photo_file = await update.message.photo[-1].get_file()
        image_bytearray = await photo_file.download_as_bytearray()

        image_part = types.Part.from_bytes(data=bytes(image_bytearray), mime_type="image/jpeg")
        prompt = "Rasmdagi matnni o'zbek tiliga tarjima qil. Ortiqcha izoh yozma."
        
        response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, image_part])
        await status_msg.edit_text(response.text if response.text else "Matn topilmadi.")
    except Exception as e:
        logger.error(f"Rasm xatosi: {e}")
        await update.message.reply_text("Rasm tahlilida xatolik yuz berdi.")

# ==============================
# 5️⃣ SOZ MATN TARJIMASI
# ==============================
async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    status_msg = await update.message.reply_text("⏳ Matn o'zbek tiliga tarjima qilinmoqda...")

    try:
        prompt = f"Berilgan matnni o'zbek tiliga professional tarjima qiling. Ortiqcha so'z qo'shmang:\n\n{update.message.text}"
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        await status_msg.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=response.text[:3500])
    except Exception as e:
        logger.error(f"Tarjima xatosi: {e}")
        await status_msg.edit_text("Tarjimada texnik xatolik ketdi.")

# ==============================
# 🎬 VIDEO TARJIMA FUNKSIYASI (whisper + gemini)
# ==============================
async def handle_video_translation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if video.duration > 120:
        await update.message.reply_text("❌ Kechirasiz, video davomiyligi eng ko'pi bilan 2 minut bo'lishi kerak!")
        return

    status_message = await update.message.reply_text("⏳ Video yuklab olinmoqda...")
    video_path = "user_video.mp4"
    audio_path = "extracted_audio.mp3"
    frame_path = "video_frame.jpg"

    try:
        # 1. Videoni yuklab olish
        video_file = await context.bot.get_file(video.file_id)
        await video_file.download_to_drive(video_path)

        clip = VideoFileClip(video_path)

        # ------------------------------------
        # 🎙️ 1-QISMM: OVOZNI MATNGA O'GIRISH (WHISPER)
        # ------------------------------------
        await status_message.edit_text("🎵 Videodan audio ajratib olinmoqda...")
        clip.audio.write_audiofile(audio_path, logger=None)

        await status_message.edit_text("🗣️ Ovoz matnga o'girilmoqda (Whisper AI)...")
        result = whisper_model.transcribe(audio_path)
        voice_text = result.get("text", "").strip()

        # ------------------------------------
        # 🖼️ 2-QISMM: EKRANDAGI MATNNI ANIQLASH (GEMINI VISION)
        # ------------------------------------
        await status_message.edit_text("🔍 Video ekranidagi yozuvlar (subtitrlar) tahlil qilinmoqda...")
        
        # Videoning aynan o'rtasidan (yoki 2-soniyasidan) bitta kadr (skrinshot) olamiz
        frame_time = min(2.0, clip.duration / 2)
        clip.save_frame(frame_path, t=frame_time)
        clip.close() # Klipni yopamiz

        # Kadrni bayt ko'rinishida o'qiymiz
        with open(frame_path, "rb") as f:
            frame_bytes = f.read()

        image_part = types.Part.from_bytes(data=bytes(frame_bytes), mime_type="image/jpeg")
        
        prompt_vision = (
            "Ushbu video kadr ichida ko'rinib turgan har qanday matnni, subtitrni yoki slayd yozuvlarini "
            "aniqlab, ularni o'zbek tiliga ma'noli qilib tarjima qilib ber. "
            "Agar rasmda umuman yozuv bo'lmasa, shunchaki 'Ekrandagi yozuvlar: Matn topilmadi' deb qaytar."
        )
        
        response_vision = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt_vision, image_part])
        screen_text = response_vision.text.strip() if response_vision.text else "Matn topilmadi."

        # ------------------------------------
        # 📝 3-QISMM: NATIJALARNI BIRLASHTIRISH
        # ------------------------------------
        await status_message.edit_text("🤖 Yakuniy natija tayyorlanmoqda...")

        final_response = "🎬 **Video tahlili natijasi:**\n\n"
        
        if voice_text:
            final_response += f"🗣️ **Gapirilgan ovoz tarjimasi (Whisper):**\n_{voice_text}_\n\n"
        else:
            final_response += "🗣️ **Gapirilgan ovoz tarjimasi:**\n_Videoda aniq gapirilgan ovoz topilmadi._\n\n"
            
        final_response += f"📺 **Ekrandagi yozuvlar/Subtitr tarjimasi (Gemini Vision):**\n{screen_text}"

        # Foydalanuvchiga yuborish
        await status_message.edit_text(final_response[:4000])

    except Exception as e:
        logger.error(f"Video multimodal xatosi: {e}")
        await status_message.edit_text(f"❌ Video qayta ishlashda xato yuz berdi: {str(e)}")
    finally:
        # Vaqtinchalik fayllarni tozalash
        if os.path.exists(video_path): os.remove(video_path)
        if os.path.exists(audio_path): os.remove(audio_path)
        if os.path.exists(frame_path): os.remove(frame_path)
# ==============================
# 🌐 6️⃣ FASTAPI YO'LAKLARI
# ==============================
@app.get("/", response_class=HTMLResponse)
async def root_status():
    return html_shablon

@app.post("/api/v1/app-process")
async def independent_app_handler(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        image_part = types.Part.from_bytes(data=bytes(file_bytes), mime_type=file.content_type)
        prompt = "Ushbu tasvirdagi matnlarni o'zbek tiliga terminologik aniqlikda o'gir va mukammal tahlil qil."
        response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, image_part])
        return {"status": "success", "data": response.text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ==============================
# ⚡ 7️⃣ LIFESPAN & BACKGROUND EVENT
# ==============================
from contextlib import asynccontextmanager

async def run_bot_in_background():
    await asyncio.sleep(3)  # Port to'liq ochilishi uchun kutish
    
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start_handler))
    bot_app.add_handler(CallbackQueryHandler(button_callback_handler))
    bot_app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    bot_app.add_handler(MessageHandler(filters.Document.PDF, analyze_pdf))
    bot_app.add_handler(MessageHandler(filters.VIDEO, handle_video_translation))  # To'g'rilangan joy 🟢
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))

    try:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        print("🤖 Telegram Bot fonda muvaffaqiyatli uchdi!")
    except Exception as e:
        logger.error(f"Botni fonda yoqishda xato: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.ensure_future(run_bot_in_background())
    yield
    print("🌐 Server to'xtatildi.")

app.router.lifespan_context = lifespan
