import os
import io
import logging
import warnings
import asyncio  # Asinxron oqimlar bilan ishlash uchun qo'shildi
from dotenv import load_dotenv

# CPU serverlarda ogohlantirishlarni o'chirish (Railway uchun)
warnings.filterwarnings("ignore", category=UserWarning)

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

# Log sozlamalari
logger = logging.getLogger(__name__)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

print("⏳ Whisper modeli yuklanmoqda...")
whisper_model = whisper.load_model("tiny")
print("✅ Whisper modeli tayyor!")


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
        f"🎬 <b>Video tarjima:</b> Videoning faqat yozuvlarini, ovozini yoki ikkalasini ham tarjima qila olaman!\n\n"
        f"<i>💡 To'g'ridan-to'g'ri biron bir matn, PDF, rasm yoki video yuborib sinab ko'ring!</i>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Matn tarjimasi", callback_data="help_translation"),
            InlineKeyboardButton("📄 PDF tahlili", callback_data="help_pdf")
        ],
        [
            InlineKeyboardButton("🖼 Rasm (Vision)", callback_data="help_vision")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text=welcome_text, reply_markup=reply_markup, parse_mode="HTML")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_translation":
        await query.message.reply_text("📝 Matnni to'g'ridan-to'g'ri yuboring, avtomatik o'zbekchaga o'giriladi.")
        return
    elif query.data == "help_pdf":
        await query.message.reply_text("📄 Chet tilidagi PDF kitobni fayl shaklida yuboring.")
        return
    elif query.data == "help_vision":
        await query.message.reply_text("🖼 Yozuvi bor istalgan rasmni yuboring.")
        return

    # 🟢 VIDEO TUGMALARI MULTIMODAL LOGIKASI (QOTMAYDIGAN ASINXRON VARIANT)
    if query.data in ["vid_only_text", "vid_only_voice", "vid_both"]:
        video_id = context.user_data.get("current_video_id")
        video_duration = context.user_data.get("current_video_duration", 10)
        
        if not video_id:
            await query.message.edit_text("❌ Video ma'lumotlari eskirgan. Iltimos, videoni qayta yuboring.")
            return

        status_message = await query.message.edit_text("⏳ Video yuklab olinmoqda...")
        video_path = "user_video.mp4"
        audio_path = "extracted_audio.mp3"
        frame_path = "video_frame.jpg"

        try:
            video_file = await context.bot.get_file(video_id)
            await video_file.download_to_drive(video_path)
            
            # Video obyektini yuklaymiz
            clip = VideoFileClip(video_path)

            voice_text = ""
            screen_text = ""

            # A) Whisper orqali Ovozni matnga o'girish
            if query.data in ["vid_only_voice", "vid_both"]:
                await status_message.edit_text("🎵 Ovoz ajratib olinmoqda...")
                # Bloklamaslik uchun alohida thread'ga beriladi
                await asyncio.to_thread(clip.audio.write_audiofile, audio_path, logger=None)
                
                await status_message.edit_text("🎙️ Matnga o'girilmoqda (Whisper AI)...")
                # Whisper transkritsiyasini ham oqimga beramiz (Asosiy qotish shu yerda edi)
                result = await asyncio.to_thread(whisper_model.transcribe, audio_path, fp16=False)
                raw_voice_text = result.get("text", "").strip()
                
                if raw_voice_text:
                    await status_message.edit_text("✨ Tarjima shakllantirilmoqda...")
                    voice_prompt = f"""Ushbu xorijiy tildagi audio matnni o'zbek tiliga chiroyli va professional darajada tarjima qilib ber.
Sizdan javobni aniq mana bu tartibda qaytarishingizni talab qilaman:

Original matn:
[Bu yerga audio matnning xorijiy tildagi o'z holatini yozing]

Tarjimasi:
[Bu yerga o'zbekcha ma'noviy tarjimasini yozing]

⚠️ TAQIQLANADI: Umuman qora harflar (bold, **, __) yoki boshqa sarlavhalar ishlatma! Faqat yuqoridagi andozada javob qaytar.

Audio matn: {raw_voice_text}"""
                    response_voice = client.models.generate_content(model='gemini-2.5-flash', contents=voice_prompt)
                    voice_text = response_voice.text.strip() if response_voice.text else ""

            # B) Gemini Vision orqali ekrandagi matnni aniqlash
            if query.data in ["vid_only_text", "vid_both"]:
                await status_message.edit_text("🔍 Ekrandagi yozuvlar tahlil qilinmoqda...")
                frame_time = min(2.0, video_duration / 2)
                
                # Kadrni saqlashni ham oqimga olamiz
                await asyncio.to_thread(clip.save_frame, frame_path, t=frame_time)
                
                with open(frame_path, "rb") as f:
                    frame_bytes = f.read()

                image_part = types.Part.from_bytes(data=bytes(frame_bytes), mime_type="image/jpeg")
                prompt_vision = f"""Ushbu video kadr ichidagi matn, subtitr yoki slayd yozuvlarini aniqlab, o'zbek tiliga chiroyli tarjima qilib ber.
Sizdan javobni aniq mana bu tartibda qaytarishingizni talab qilaman:

Original matn:
[Bu yerga rasmdagi matnning xorijiy tildagi o'z holatini yozing]

Tarjimasi:
[Bu yerga o'zbekcha ma'noviy tarjimasini yozing]

⚠️ TAQIQLANADI: Umuman qora harflar (bold, **, __) yoki boshqa sarlavhalar ishlatma! Faqat yuqoridagi andozada javob qaytar."""
                
                response_vision = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt_vision, image_part])
                screen_text = response_vision.text.strip() if response_vision.text else ""

            # Resurslarni yopamiz
            clip.close()

            # 📝 Natijani yig'ish (Sarlavha faqat "Videodagi text:")
            final_response = "Videodagi text:\n\n"
            
            if query.data == "vid_only_text":
                final_response += screen_text if screen_text else "Matn topilmadi."
            elif query.data == "vid_only_voice":
                final_response += voice_text if voice_text else "Ovozli matn aniqlanmadi."
            elif query.data == "vid_both":
                combined_text = ""
                if voice_text:
                    combined_text += f"[OVOZDAN OLINGAN]\n{voice_text}\n\n"
                if screen_text:
                    combined_text += f"[EKRANDAN OLINGAN]\n{screen_text}"
                final_response += combined_text if combined_text else "Videodan hech qanday matn aniqlanmadi."

            await status_message.edit_text(final_response[:4000])

        except Exception as e:
            logger.error(f"Tugma video xatosi: {e}")
            await status_message.edit_text(f"❌ Xatolik yuz berdi: {str(e)}")
        finally:
            # Fayllar ochiq qolib ketishini oldini olish
            try:
                if 'clip' in locals(): clip.close()
            except: pass
            
            if os.path.exists(video_path): os.remove(video_path)
            if os.path.exists(audio_path): os.remove(audio_path)
            if os.path.exists(frame_path): os.remove(frame_path)

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
            
            prompt = f"""Foydalanuvchi xuddi kitobni oʻqigandek boʻlsin. 
Kitob ichini analiz qilganingda eng yorqin boʻlgan matnlarni tushuntirganingdan keyin yozib qoʻy. 
Ortiqcha belgilarga e’tibor qaratma va oʻzing ham bu belgilarni ishlatma. 

⚠️ MUTLAQ TAQIQ: Qora shriftdagi harflar kerak emas (umuman ** yoki __ belgilarini ishlatma). 
Foydalanuvchi uzun matnlarni yomon koʻradi. Qora harf va soʻzlardan foydalanma. Context kerak emas. Xulosa ham. 
HECH QANDAY sarlavha, kirish soʻzi (masalan: ‘Hujjat mazmuni’, ‘Mana tahlil’) yozma! 

Oxirida bu pdf hujjat yoki kitob kimlar uchun foydali ekanligini ham chiqar.

Hujjat matni:
{clean_text[:12000]}"""
            
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
        
        prompt = f"""Rasmdagi matnni oʻzbek tiliga tarjima qil. 
Soʻzlarni shunchaki tarjima qilma, umumiy ma’nosini yetkaz. 
⚠️ TAQIQLANADI: Qora harflarni ishlatma (umuman ** yoki __ belgisidan foydalanma). 

Agar rasmda ajratilgan biror belgi boʻlsa oʻshani qoʻyishing mumkin. 
Sen oʻzing ortiqcha deb belgilagan yoki rasmda ortiqchadek tuyulgan belgilar shartmas."""
        
        response = client.models.generate_content(model='gemini-2.5-flash', contents=[prompt, image_part])
        result_text = response.text.strip() if response.text else ""
        
        if result_text:
            await status_msg.delete()
            await context.bot.send_message(chat_id=update.effective_chat.id, text=result_text[:3500])
        else:
            await status_msg.edit_text("🤷‍♂️ Kechirasiz, rasmdan o'qish uchun hech qanday matn topilmadi.")
        
    except Exception as e:
        logger.error(f"Rasm xatosi: {e}")
        error_str = str(e)
        if "503" in error_str or "high demand" in error_str.lower() or "unavailable" in error_str.lower():
            await status_msg.edit_text("⚠️ Google Gemini serverlarida ayni damda yuklama juda yuqori. Iltimos, 1-2 daqiqadan so'ng qayta urinib ko'ring!")
        else:
            try:
                await status_msg.edit_text("❌ Rasm tahlilida kutilmagan xatolik yuz berdi.")
            except Exception:
                await update.message.reply_text("❌ Rasm tahlilida kutilmagan xatolik yuz berdi.")

# ==============================
# 5️⃣ SOZ MATN TARJIMASI
# ==============================
async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: 
        return
        
    status_msg = await update.message.reply_text("⏳ Matn o'zbek tiliga tarjima qilinmoqda...")

    try:
        prompt = f"""Siz professional va yuqori malakali sinxron tarjimonsiz. 
Vazifangiz berilgan matnni qaysi tilda boʻlishidan qat’i nazar oʻzbek tiliga mukammal va professional darajada tarjima qilish. Ortiqcha izoh yoki qo'shimcha gaplar qo'shmang.
Soʻzlarni shunchaki tarjima qilmasdan umumiy ma’nosini yetkazing.

⚠️ TAQIQLANADI: Umuman qora harflardan (**, __) foydalanmang!

Matn:
{update.message.text}"""

        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        
        await status_msg.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=response.text[:3500])
        
    except Exception as e:
        logger.error(f"Tarjima xatosi: {e}")
        error_str = str(e)
        if "503" in error_str or "high demand" in error_str.lower() or "unavailable" in error_str.lower():
            await status_msg.edit_text("⚠️ Google Gemini serverlarida ayni damda yuklama juda yuqori. Iltimos, 1-2 daqiqadan so'ng qayta urinib ko'ring!")
        else:
            await status_msg.edit_text("❌ Tarjimada texnik xatolik ketdi. Birozdan so'ng qayta urinib ko'ring.")

# ==============================
# 🎬 VIDEO KELGANDA TUGMALARNI CHIQARISH
# ==============================
async def handle_video_translation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video
    if video.duration > 120:
        await update.message.reply_text("❌ Kechirasiz, video davomiyligi eng ko'pi bilan 2 minut bo'lishi kerak!")
        return

    context.user_data["current_video_id"] = video.file_id
    context.user_data["current_video_duration"] = video.duration

    keyboard = [
        [
            InlineKeyboardButton("📺 Faqat ekrandagi matn (Subtitr)", callback_data="vid_only_text"),
            InlineKeyboardButton("🎙️ Faqat gapirilgan ovoz", callback_data="vid_only_voice")
        ],
        [
            InlineKeyboardButton("🎬 Ikkalasini ham (To'liq tahlil)", callback_data="vid_both")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text="🎬 Video qabul qilindi!\nUshbu videoning qaysi qismini tarjima qilishni xohlaysiz?",
        reply_markup=reply_markup
    )

# ==============================
# ⚡ 6️⃣ ASOSIY ISHGA TUSHIRISH (MAIN)
# ==============================
def main():
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start_handler))
    bot_app.add_handler(CallbackQueryHandler(button_callback_handler))
    bot_app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    bot_app.add_handler(MessageHandler(filters.Document.PDF, analyze_pdf))
    bot_app.add_handler(MessageHandler(filters.VIDEO, handle_video_translation))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))

    print("🤖 Telegram Bot SOF Polling rejimida muvaffaqiyatli uchdi!")
    bot_app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
