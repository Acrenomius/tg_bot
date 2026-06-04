import os
import io
import logging
import asyncio
from dotenv import load_dotenv

# FastAPI kutubxonalari (Ilova API yo'lagi uchun)
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

# Yangi rasmiy Google SDK (Gemini uchun)
from google import genai
from google.genai import types

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

# FastAPI veb-server obyekti (Alohida ilova ulanishi uchun)
app = FastAPI(title="Universal AI Translator Platform API")

# Har qanday qurilma (Ilova) ulanishi uchun CORS ruxsatnomalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


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
        f"📝 <b>Matnli tarjima:</b> Istalgan tildagi uzun matn yoki gaplarni yuboring, men ularni akademik va badiiy jihatdan o'zbekcha qilaman.\n"
        f"📄 <b>PDF Hujjatlar tarjimasi:</b> Xorijiy tildagi kitob yoki maqolalarni o'qib, o'zbek tilida tahliliy sharh tayyorlayman.\n"
        f"🖼 <b>Tasvirlardagi matn (Vision):</b> Yuborgan rasmingiz ichidagi chet tillaridagi yozuvlarni aniqlab, o'zbekchaga o'giraman.\n\n"
        f"<i>💡 To'g'ridan-to'g'ri menga biron bir matn, PDF fayl yoki rasm yuborib sinab ko'ring!</i>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Matn tarjima qilish", callback_data="help_translation"),
            InlineKeyboardButton("📄 PDF tahlil qilish", callback_data="help_pdf")
        ],
        [
            InlineKeyboardButton("🖼 Rasm tahlili (Vision)", callback_data="help_vision")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text=welcome_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_translation":
        await query.message.reply_text(
            "📝 <b>Matn tarjima qilish bo'limi:</b>\n\n"
            "Menga istalgan tildagi (ingliz, rus, nemis va h.k.) matnni to'g'ridan-to'g'ri yuboring. "
            "Tizim xabaringizni qabul qilishi bilan avtomatik ravishda kontekstual sinxron tarjimani boshlaydi.",
            parse_mode="HTML"
        )
    elif query.data == "help_pdf":
        await query.message.reply_text(
            "📄 <b>PDF tahlil qilish bo'limi:</b>\n\n"
            "Menga chet tilidagi elektron kitob yoki PDF hujjatni fayl ko'rinishida yuboring. "
            "Men uning matnini to'liq tahlil qilib, o'zbek tilida sizga mazmunini tushuntirib beraman.",
            parse_mode="HTML"
        )
    elif query.data == "help_vision":
        await query.message.reply_text(
            "🖼 <b>Computer Vision (Rasm tarjimasi) bo'limi:</b>\n\n"
            "Menga istalgan rasmni yuboring. Men undagi xorijiy yozuvlarni "
            "o'zbek tiliga kontekstual ma'nosini buzmagan holda o'girib beraman.",
            parse_mode="HTML"
        )


# ==============================
# 3️⃣ PDF TAHLILI FUNKSIYASI
# ==============================
async def analyze_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return
    if not update.message.document.file_name.lower().endswith('.pdf'):
        return

    status_msg = await update.message.reply_text("PDF qabul qilindi. Matn o'qilmoqda... 📄")
    file = await update.message.document.get_file()

    try:
        pdf_bytes = await file.download_as_bytearray()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()

        clean_text = full_text.strip()
        
        if len(clean_text) > 10:
            await status_msg.edit_text("Hujjat tahlil qilinmoqda... ✨")
            
            prompt = (
                "Foydalanuvchi xuddi kitobni o'qigandek bo'lsin. "
                "Kitob ichidagi o'qilganda eng yorqin bo'lgan matnlarni tushuntirganingdan keyin yozib qo'y. "
                "Ortiqcha belgilarga e'tibor qaratma va o'zing ham bu belgilarni ishlatma. Qora shriftdagi harflar kerak emas. "
                "Foydalanuvchi uzun matnlarni yomon ko'radi. Qora harf va so'zlardan foydalanma. Context kerak emas. Xulosa ham. "
                "HECH QANDAY sarlavha, kirish so'zi (masalan: 'Hujjat mazmuni', 'Mana tahlil') yozma! "
                "Oxirida bu pdf hujjat yoki kitob kimlar uchun foydali ekanligini ham chiqar.\n\n"
                f"Matn: {clean_text[:12000]}"  # Resurs limitidan oshmaslik uchun xavfsiz chegara
            )
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            final_output = response.text.strip() if response.text else ""
            
            filter_words = ["Hujjatning qisqacha mazmuni:", "Hujjat mazmuni:", "Tahlil:", "**Hujjatning qisqacha mazmuni:**"]
            for word in filter_words:
                if final_output.startswith(word):
                    final_output = final_output.replace(word, "", 1).strip()

            if final_output:
                await status_msg.delete()
                
                text_to_send = final_output
                max_length = 3500
                chat_id = update.effective_chat.id
                
                while len(text_to_send) > 0:
                    if len(text_to_send) <= max_length:
                        await context.bot.send_message(chat_id=chat_id, text=text_to_send)
                        break
                    
                    split_index = text_to_send.rfind('\n', 0, max_length)
                    if split_index == -1 or split_index == 0:
                        split_index = text_to_send.rfind('. ', 0, max_length)
                    if split_index == -1 or split_index == 0:
                        split_index = text_to_send.rfind(' ', 0, max_length)
                    if split_index == -1 or split_index == 0:
                        split_index = max_length
                        
                    chunk = text_to_send[:split_index].strip()
                    if chunk:
                        await context.bot.send_message(chat_id=chat_id, text=chunk)
                    
                    text_to_send = text_to_send[split_index:].strip()
            else:
                await status_msg.edit_text("Tahlil natijasini olishda muammo bo'ldi.")
            
        else:
            await status_msg.edit_text("PDF ichida o'qish uchun matn topilmadi.")

    except Exception as e:
        logger.error(f"PDF xatosi: {e}")
        try:
            await status_msg.edit_text("PDF tahlilida texnik xatolik yuz berdi.")
        except Exception:
            await update.message.reply_text("PDF tahlilida xatolik yuz berdi.")


# ==============================
# 4️⃣ MULTIMODAL (RASM) FUNKSIYASI
# ==============================
async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        status_msg = await update.message.reply_text("Rasm o'qilmoqda va matn aniqlanmoqda... 🔍")
        photo_file = await update.message.photo[-1].get_file()
        image_bytearray = await photo_file.download_as_bytearray()

        image_part = types.Part.from_bytes(
            data=bytes(image_bytearray),
            mime_type="image/jpeg"
        )
        
        prompt = (
            "Rasmdagi matnni o'zbek tiliga tarjima qil. "
            "So'zlarni shunchaki tarjima qilma, umumiy ma'nosini yetkaz. "
            "Qora harflarni ishlatma. Agar rasmda ajratilgan biror belgi bo'lsa o'shani qo'yishing mumkin. "
            "Sen o'zing ortiqcha deb belgilagan yoki rasmda ortiqchadek tuyulgan belgilar shartmas."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image_part]
        )
        await status_msg.edit_text(response.text if response.text else "Rasmda tarjima qilinadigan matn topilmadi.")
    except Exception as e:
        logger.error(f"Rasm xatosi: {e}")
        await update.message.reply_text("Rasm tahlilida xatolik yuz berdi.")


# ==============================
# 5️⃣ SOZ MATN TARJIMASI
# ==============================
async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_text = update.message.text
    status_msg = await update.message.reply_text("⏳ Matn o'zbek tiliga tarjima qilinmoqda...")

    try:
        prompt = (
            "Siz professional va yuqori malakali sinxron tarjimonsiz. Vazifangiz berilgan matnni "
            "qaysi tilda bo'lishidan qat'i nazar (ingliz, rus va h.k.) o'zbek tiliga mukammal tarjima qilish.\n"
            "DIQQAT: O'zingizdan hech qanday izoh, 'Mana tarjima' kabi kirish so'zlari yoki xulosa qo'shmang! "
            "Faqat tarjimaning o'zini qaytaring.\n\n"
            f"Tarjima qilinishi kerak bo'lgan matn:\n{user_text}"
        )

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        final_translation = response.text.strip() if response.text else ""

        if final_translation:
            await status_msg.delete()
            
            text_to_send = final_translation
            max_length = 3500
            chat_id = update.effective_chat.id
            
            while len(text_to_send) > 0:
                if len(text_to_send) <= max_length:
                    await context.bot.send_message(chat_id=chat_id, text=text_to_send)
                    break
                
                split_index = text_to_send.rfind('\n', 0, max_length)
                if split_index == -1 or split_index == 0:
                    split_index = text_to_send.rfind('. ', 0, max_length)
                if split_index == -1 or split_index == 0:
                    split_index = text_to_send.rfind(' ', 0, max_length)
                if split_index == -1 or split_index == 0:
                    split_index = max_length
                    
                chunk = text_to_send[:split_index].strip()
                if chunk:
                    await context.bot.send_message(chat_id=chat_id, text=chunk)
                
                text_to_send = text_to_send[split_index:].strip()
        else:
            await status_msg.edit_text("Matnni tarjima qilishda muammo yuz berdi.")

    except Exception as e:
        logger.error(f"Tarjima xatosi: {e}")
        try:
            await status_msg.edit_text("Xabarni tarjima qilishda tizimli xatolik yuz berdi.")
        except Exception:
            await update.message.reply_text("Tizimli xatolik yuz berdi.")


# ==============================
# 🌐 6️⃣ FASTAPI YO'LAKLARI (ALOHIDA MOBIL ILOVA UCHUN API)
# ==============================

@app.get("/")
async def root_status():
    return {"status": "running", "platform": "Universal AI Center"}

@app.post("/api/v1/app-process")
async def independent_app_handler(file: UploadFile = File(...)):
    """
    Alohida kiber-neon mobil ilovadan (App) keladigan rasm yoki fayllarni 
    qabul qilib, Gemini API'ga yuboruvchi mustaqil ochiq yo'lak (API Endpoint).
    """
    try:
        file_bytes = await file.read()
        
        # Fayl turini aniqlash (Mime Type)
        mime_type = file.content_type
        
        image_part = types.Part.from_bytes(
            data=bytes(file_bytes),
            mime_type=mime_type
        )
        
        prompt = (
            "Siz alohida mobil ilovaning intellektual yadrosisiz. "
            "Ushbu kelgan texnik hujjat yoki tasvirdagi matnlarni o'zbek tiliga terminologik aniqlikda o'gir va mukammal tahlil qil."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image_part]
        )
        
        return {
            "status": "success",
            "data": response.text if response.text else "Ma'lumot topilmadi."
        }
    except Exception as e:
        logger.error(f"App API xatosi: {e}")
        return {"status": "error", "message": str(e)}


# ==============================
# ⚡ 7️⃣ BACKGROUND EVENT (FASTAPI ISHGA TUSHGANDA BOTNI HAM QO'SHIB YONDIRISH)
# ==============================

@app.on_event("startup")
async def startup_event():
    """
    FastAPI server (Railway) yonganda Telegram bot polling xizmatini 
    orqa fonda asinxron ravishda birga ishga tushiradi.
    """
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start_handler))
    bot_app.add_handler(CallbackQueryHandler(button_callback_handler))
    bot_app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    bot_app.add_handler(MessageHandler(filters.Document.PDF, analyze_pdf))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))

    # Pollingni FastAPI asinxron sikli ichida xavfsiz ishga tushirish
    asyncio.create_task(bot_app.initialize())
    asyncio.create_task(bot_app.updater.start_polling())
    asyncio.create_task(bot_app.start())
    print("🤖 Telegram Bot orqa fonda parallel muvaffaqiyatli ishga tushdi (Background Polling)...")
