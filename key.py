import os
import io
import logging
import warnings
import asyncio
from dotenv import load_dotenv

# CPU serverlarda ogohlantirishlarni o'chirish
warnings.filterwarnings("ignore", category=UserWarning)

from google import genai
from google.genai import types
from google.genai.errors import APIError  # Xatoliklarni ushlash uchun

from moviepy import VideoFileClip
import fitz  # PyMuPDF

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

if not TOKEN or not GEMINI_KEY:
    raise ValueError("XATOLIK: Token yoki API kalit muhit o'zgaruvchilarida topilmadi!")

client = genai.Client(api_key=GEMINI_KEY)

logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ⚠️ DIQQAT: Whisper o'chirib tashlandi! RAM endi to'lib ketmaydi.

# ==============================
# 🔄 GEMINI CHAQIRUVLARINI HIMOYA QILISH (RETRY LOGIC)
# ==============================
async def generate_content_with_retry(model, contents, retries=3, backoff_in_seconds=2):
    """Gemini API 503 yoki yuklama xatosi berganda qayta urinish funksiyasi"""
    for attempt in range(retries):
        try:
            # Sinxron API chaqiruvini thread'da xavfsiz bajaramiz
            response = await asyncio.to_thread(
                client.models.generate_content, model=model, contents=contents
            )
            return response
        except APIError as e:
            if attempt == retries - 1:
                raise e
            # Agar 503 yoki yuklama xatosi bo'lsa, biroz kutib qayta urinamiz
            logger.warning(
                f"Gemini API xatolik berdi ({e.code}). {backoff_in_seconds} soniyadan keyin qayta urinish {attempt+1}/{retries}..."
            )
            await asyncio.sleep(backoff_in_seconds)
            backoff_in_seconds *= 2  # Kutish vaqtini ko'paytiramiz

# ==============================
# 2️⃣ COMMAND VA CALLBACK HANDLERLAR
# ==============================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    welcome_text = (
        f"👋 <b>Assalomu alaykum, {user_name}!</b>\n\n"
        f"🤖 Men — <b>Gemini 2.5</b> universal tarjimon asistentman.\n\n"
        f"<i>💡 Menga matn, rasm, PDF yoki qisqa video yuborishingiz mumkin!</i>"
    )
    keyboard = [
        [InlineKeyboardButton("📝 Matn tarjimasi", callback_data="help_translation"),
         InlineKeyboardButton("📄 PDF tahlili", callback_data="help_pdf")],
        [InlineKeyboardButton("🖼 Rasm (Vision)", callback_data="help_vision")]
    ]
    await update.message.reply_text(
        text=welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
    )

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("help_"):
        messages = {
            "help_translation": "📝 Matnni to'g'ridan-to'g'ri yuboring.",
            "help_pdf": "📄 Chet tilidagi PDF faylni yuboring.",
            "help_vision": "🖼 Yozuvi bor istalgan rasmni yuboring."
        }
        await query.message.reply_text(messages.get(query.data, ""))
        return

    # 🟢 VIDEO QAYTA ISHLASH (RAM-XAVFSIZ VA RECOVERY LOGIKALI)
    if query.data in ["vid_only_text", "vid_only_voice", "vid_both"]:
        video_id = context.user_data.get("current_video_id")
        video_duration = context.user_data.get("current_video_duration", 10)
        
        if not video_id:
            await query.message.edit_text("❌ Video ma'lumotlari eskirgan. Qayta yuboring.")
            return

        status_message = await query.message.edit_text("⏳ Video serverga yuklab olinmoqda...")
        video_path = "user_video.mp4"
        audio_path = "extracted_audio.mp3"
        frame_path = "video_frame.jpg"

        try:
            video_file = await context.bot.get_file(video_id)
            await video_file.download_to_drive(video_path)
            
            clip = VideoFileClip(video_path)
            voice_text = ""
            screen_text = ""

            # A) Ovozni to'g'ridan-to'g'ri Gemini'ga berib yuboramiz (Whisper-siz!)
            if query.data in ["vid_only_voice", "vid_both"]:
                await status_message.edit_text("🎵 Ovoz ajratib olinmoqda...")
                await asyncio.to_thread(clip.audio.write_audiofile, audio_path, logger=None)
                
                await status_message.edit_text("🎙️ Ovoz Gemini AI orqali tarjima qilinmoqda...")
                
                with open(audio_path, "rb") as f:
                    audio_bytes = f.read()
                
                audio_part = types.Part.from_bytes(data=bytes(audio_bytes), mime_type="audio/mp3")
                voice_prompt = """Ushbu audio fayl ichidagi nutqni (gaplarni) tingla, aniqla va o'zbek tiliga chiroyli, professional darajada tarjima qilib ber.
⚠️ TAQIQLANADI: Umuman qora harflar (bold, **, __) yoki sarlavhalar ishlatma! Faqat toza tarjimani o'zini qaytar."""
                
                response_voice = await generate_content_with_retry(
                    model='gemini-2.5-flash', contents=[voice_prompt, audio_part]
                )
                voice_text = response_voice.text.strip() if response_voice.text else ""

            # B) Gemini Vision kadr tahlili
            if query.data in ["vid_only_text", "vid_both"]:
                await status_message.edit_text("🔍 Ekrandagi yozuvlar tahlil qilinmoqda...")
                frame_time = min(2.0, video_duration / 2)
                await asyncio.to_thread(clip.save_frame, frame_path, t=frame_time)
                
                with open(frame_path, "rb") as f:
                    frame_bytes = f.read()

                image_part = types.Part.from_bytes(data=bytes(frame_bytes), mime_type="image/jpeg")
                prompt_vision = """Ushbu video kadr ichidagi matn yoki subtitrlarni aniqlab, o'zbek tiliga chiroyli tarjima qilib ber.
⚠️ TAQIQLANADI: Umuman qora harflar (bold, **, __) yoki sarlavhalar ishlatma! Faqat toza tarjimani yoz."""
                
                response_vision = await generate_content_with_retry(
                    model='gemini-2.5-flash', contents=[prompt_vision, image_part]
                )
                screen_text = response_vision.text.strip() if response_vision.text else ""

            clip.close()

            # 📝 Natijani yig'ish (Siz istagandek toza HTML formatda)
            final_response = "<b>Videodagi text:</b>\n\n"
            if query.data == "vid_only_text":
                final_response += screen_text if screen_text else "Matn topilmadi."
            elif query.data == "vid_only_voice":
                final_response += voice_text if voice_text else "Ovozli matn aniqlanmadi."
            elif query.data == "vid_both":
                if voice_text:
                    final_response += f"<i>[OVOZDAN OLINGAN]</i>\n{voice_text}\n\n"
                if screen_text:
                    final_response += f"<i>[EKRANDAN OLINGAN]</i>\n{screen_text}"
                if not voice_text and not screen_text:
                    final_response = "Videodan hech qanday matn aniqlanmadi."

            await status_message.edit_text(final_response[:4000], parse_mode="HTML")

        except Exception as e:
            logger.error(f"Tugma video xatosi: {e}")
            await status_message.edit_text(f"❌ Xatolik yuz berdi: Gemini serveri band yoki fayl formati mos kelmadi.")
        finally:
            try:
                if 'clip' in locals(): clip.close()
            except: pass
            if os.path.exists(video_path): os.remove(video_path)
            if os.path.exists(audio_path): os.remove(audio_path)
            if os.path.exists(frame_path): os.remove(frame_path)

# ==============================
# 3️⃣ PDF, RASM VA MATN HANDLERLARI (RETRY QO'SHILGAN VARIANTI)
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
            prompt = f"Hujjatni o'zbekcha qisqa tahlil qil. Qora harf (**), kirish so'zlari, sarlavhalar ishlatma:\n\n{clean_text[:12000]}"
            
            response = await generate_content_with_retry(model='gemini-2.5-flash', contents=prompt)
            final_output = response.text.strip() if response.text else "Tahlil natijasi bo'sh."
            
            await status_msg.delete()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=final_output[:3500], parse_mode="HTML")
        else:
            await status_msg.edit_text("PDF ichida o'qish uchun matn topilmadi.")
    except Exception as e:
        logger.error(f"PDF xatosi: {e}")
        await status_msg.edit_text("⚠️ PDF tahlilida yuklama xatosi bo'ldi. Birozdan so'ng qayta urinib ko'ring.")

async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        status_msg = await update.message.reply_text("Rasm o'qilmoqda va matn aniqlanmoqda... 🔍")
        photo_file = await update.message.photo[-1].get_file()
        image_bytearray = await photo_file.download_as_bytearray()

        image_part = types.Part.from_bytes(data=bytes(image_bytearray), mime_type="image/jpeg")
        prompt = "Rasmdagi matnni oʻzbek tiliga tarjima qil. Umuman qora harflar (**) ishlatma!"
        
        response = await generate_content_with_retry(model='gemini-2.5-flash', contents=[prompt, image_part])
        result_text = response.text.strip() if response.text else ""
        
        await status_msg.delete()
        if result_text:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=result_text[:3500], parse_mode="HTML")
        else:
            await update.message.reply_text("🤷‍♂️ Rasmdan o'qish uchun matn topilmadi.")
    except Exception as e:
        logger.error(f"Rasm xatosi: {e}")
        await status_msg.edit_text("⚠️ Google serverlarida yuklama yuqori bo'lgani sababli rasm ochilmadi. Keyinroq qayta urinib ko'ring.")

async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    status_msg = await update.message.reply_text("⏳ Matn o'zbek tiliga tarjima qilinmoqda...")
    try:
        prompt = f"Matnni o'zbek tiliga chiroyli tarjima qilib ber. Ortiqcha izoh, sarlavha va qora shrift (**) ishlatma:\n\n{update.message.text}"
        response = await generate_content_with_retry(model='gemini-2.5-flash', contents=prompt)
        await status_msg.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=response.text[:3500], parse_mode="HTML")
    except Exception as e:
        logger.error(f"Tarjima xatosi: {e}")
        await status_msg.edit_text("❌ Tarjimada texnik yuklama xatoligi ketdi. Birozdan so'ng qayta urinib ko'ring.")

async def handle_video_translation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if video.duration > 120:
        await update.message.reply_text("❌ Video davomiyligi eng ko'pi bilan 2 minut bo'lishi kerak!")
        return

    context.user_data["current_video_id"] = video.file_id
    context.user_data["current_video_duration"] = video.duration

    keyboard = [
        [InlineKeyboardButton("📺 Faqat ekrandagi matn", callback_data="vid_only_text"),
         InlineKeyboardButton("🎙️ Faqat gapirilgan ovoz", callback_data="vid_only_voice")],
        [InlineKeyboardButton("🎬 Ikkalasini ham (To'liq tahlil)", callback_data="vid_both")]
    ]
    await update.message.reply_text(
        text="🎬 Video qabul qilindi! Qaysi qismini tarjima qilamiz?", reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==============================
# ⚡ MAIN RUNNER
# ==============================
def main():
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start_handler))
    bot_app.add_handler(CallbackQueryHandler(button_callback_handler))
    bot_app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    bot_app.add_handler(MessageHandler(filters.Document.PDF, analyze_pdf))
    bot_app.add_handler(MessageHandler(filters.VIDEO, handle_video_translation))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))

    print("🤖 Bot muvaffaqiyatli uchdi!")
    bot_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
