import os
import io
import logging
from dotenv import load_dotenv

# Yangi rasmiy Google SDK (Gemini 2.5 uchun)
from google import genai
from google.genai import types

# PDF va Bepul Internet qidiruv kutubxonalari
import fitz  # PyMuPDF
from duckduckgo_search import DDGS

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

# Tokenni muhit o'zgaruvchisidan yoki xavfsiz joydan olamiz
TOKEN = os.getenv("TELEGRAM_TOKEN", "8559822278:AAFjJK95n-xQAezOz0hTPEgZPyYCRB6zlpI")

# API kalitni Railway Variables bo'limidan olish tavsiya etiladi
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBYrXFC_BDDFmnSILE-cd98eXXdZVbRL5Y")
client = genai.Client(api_key=GEMINI_KEY)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================
# 2️⃣ START KOMANDASI HANDLERI
# ==============================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Foydalanuvchi botni ishga tushirganda tizim imkoniyatlarini va
    yo'riqnomani vizual tugmalar bilan ko'rsatuvchi asinxron handler.
    """
    user_name = update.effective_user.first_name
    
    welcome_text = (
        f"👋 <b>Assalomu alaykum, {user_name}!</b>\n\n"
        f"🤖 Men — <b>Gemini 2.5</b> neyron tarmog'i negizida ishlovchi multi-funksional "
        f"intellektual asistentman. Men bilan oddiy suhbat qurishingiz yoki murakkab "
        f"multimodal vazifalarni bajarishingiz mumkin.\n\n"
        f"<b>📌 Men nimalar qila olaman?</b>\n"
        f"📝 <b>Matnli tahlil:</b> Istalgan savolingizga javob beraman, dasturlash kodlarini yozaman.\n"
        f"🌐 <b>Real vaqtda qidiruv (RAG):</b> Internetdan eng so'nggi yangiliklar va kurslarni topaman.\n"
        f"🖼 <b>Tasvirlarni aniqlash:</b> Yuborgan rasmingizni tahlil qilib, savollaringizga javob beraman.\n"
        f"📄 <b>PDF Hujjatlar bilan ishlash:</b> Kitob yoki hujjatlarni o'qib, qisqacha xulosa qilaman.\n"
        f"🎧 <b>Audio transkripsiya:</b> Ovozli yoki mp3 fayllarni eshitib, matnga o'giraman.\n\n"
        f"<i>💡 Nimadan boshlashni bilmayapsizmi? To'g'ridan-to'g'ri menga biron bir fayl, ovoz yoki matn yuboring!</i>"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🌐 Internetdan qidirish (RAG)", callback_data="help_rag"),
            InlineKeyboardButton("📄 PDF tahlil qilish", callback_data="help_pdf")
        ],
        [
            InlineKeyboardButton("🖼 Rasm va Computer Vision", callback_data="help_vision"),
            InlineKeyboardButton("🎧 Ovozli xabarlar (Audio)", callback_data="help_audio")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text=welcome_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Foydalanuvchi menyudagi interaktiv tugmalarni bosganda
    zudlik bilan javob qaytaruvchi asinxron handler.
    """
    query = update.callback_query
    # Telegram interfeysida soat rasmi aylanib qolmasligi uchun so'rovni tasdiqlaymiz
    await query.answer()
    
    # Qaysi tugma bosilganiga qarab javob matnini shakllantiramiz
    if query.data == "help_pdf":
        await query.message.reply_text(
            "📄 <b>PDF tahlil qilish bo'limi:</b>\n\n"
            "Menga istalgan elektron kitob yoki PDF hujjatni yuboring (fayl ko'rinishida).\n Men uni tadqiq qilib, sizga uni yoritib beraman"
            parse_mode="HTML"
        )
    elif query.data == "help_rag":
        await query.message.reply_text(
            "🌐 <b>Internetdan qidirish (RAG) bo'limi:</b>\n\n"
            "Matnli xabaringiz ichida <i>'top', 'qidir', 'yangilik', 'kursi', 'ob-havo'</i> "
            "kabi so'zlar qatnashsa, men avtomatik ravishda DuckDuckGo tizimi orqali global "
            "internetga ulanaman va eng aktual ma'lumotni Gemini modeliga sintez qilib beraman.",
            parse_mode="HTML"
        )
    elif query.data == "help_vision":
        await query.message.reply_text(
            "🖼 <b>Computer Vision (Rasm tahlili) bo'limi:</b>\n\n"
            "Menga istalgan rasmni yuboring. Men undagi ob'ektlarni tahlil qilaman "
            "yoki rasm ichidagi matnlarni o'zbek tiliga o'giraman.",
            parse_mode="HTML"
        )


# ==============================
# 3️⃣ PDF TAHLILI FUNKSIYASI
# ==============================
async def analyze_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
                "Quyidagi PDF hujjat matnini diqqat bilan tahlil qil va uning eng muhim qismlarini "
                "chiroyli tarzda va foydalanuvchi tushunadigan tarzda yetkaz. Foydalanuvchi xuddi kitobni o'qigandek bo'lsin. "
                "Kitob ichidagi o'qilganda eng yorqin bo'lgan matnlarni tushuntirganingdan keyin yozib qo'y. "
                "Ortiqcha belgilarga e'tibor qaratma va o'zing ham bu belgilarni ishlatma. Qora shriftdagi harflar kerak emas. "
                "Foydalanuvchi uzun matnlarni yomon ko'radi. Qora harf va so'zlardan foydalanma. Context kerak emas. Xulosa ham. "
                "HECH QANDAY sarlavha, kirish so'zi (masalan: 'Hujjat mazmuni', 'Mana tahlil') yozma! "
                f"\n\nMatn: {clean_text[:15000]}"
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
                await status_msg.edit_text(final_output)
            else:
                await status_msg.edit_text("Tahlil natijasini olishda muammo bo'ldi.")
            
        else:
            await status_msg.edit_text("PDF ichida o'qish uchun matn topilmadi.")

    except Exception as e:
        logger.error(f"PDF xatosi: {e}")
        await status_msg.edit_text("PDF tahlilida texnik xatolik yuz berdi.")

# ==============================
# 4️⃣ MULTIMODAL (RASM VA OVOZ) FUNKSIYALAR
# ==============================
async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        status_msg = await update.message.reply_text("Rasm o'qilmoqda... 🔍")
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
        await status_msg.edit_text(response.text if response.text else "Matn topilmadi.")
    except Exception as e:
        logger.error(f"Rasm xatosi: {e}")
        await update.message.reply_text("Rasm tahlilida xatolik yuz berdi.")

async def analyze_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("Ovozli xabar eshitilmoqda... 🎧")
    try:
        voice_file = await update.message.voice.get_file()
        voice_bytearray = await voice_file.download_as_bytearray()
        
        audio_part = types.Part.from_bytes(
            data=bytes(voice_bytearray),
            mime_type="audio/ogg"
        )
        
        prompt = (
            "Ushbu audio xabarni tingla va o'zbek tilida mantiqiy javob ber. "
            "Agar savol bo'lsa javob qaytar, agar shunchaki fikr bo'lsa unga munosabat bildir. "
            "Javobing samimiy va tushunarli bo'lsin."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, audio_part]
        )
        
        if response.text:
            await status_msg.edit_text(f"🎤 <b>Javob:</b>\n\n{response.text}", parse_mode="HTML")
        else:
            await status_msg.edit_text("Ovozni tushunib bo'lmadi, qaytadan yozib ko'ring.")

    except Exception as e:
        logger.error(f"Ovoz xatosi: {e}")
        await status_msg.edit_text("Ovozli xabarni tahlil qilishda texnik xatolik yuz berdi. ✨")

# ==============================
# 5️⃣ INTERNET QIDIRUV VA MATN TAHLILI (RAG)
# ==============================
def search_internet(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                query,
                region='uz-uz',
                safesearch='moderate',
                max_results=3,
                timelimit='d'
            ))
            if not results:
                return None
            search_text = "\n".join([f"{r['title']}: {r['body']}" for r in results])
            return search_text
    except Exception as e:
        logger.error(f"Qidiruv xatosi: {e}")
        return None
    
async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    trigger_words = ["top", "qidir", "search", "yangilik", "kursi", "ob-havo"]
    use_internet = any(word in user_text.lower() for word in trigger_words)

    try:
        context_text = ""
        if use_internet:
            status_msg = await update.message.reply_text("🌐 Internetdan qidirilmoqda...")
            search_data = search_internet(user_text)
            if search_data:
                context_text = f"\n\nInternetdan topilgan ma'lumotlar:\n{search_data}"
                await status_msg.delete()  # "Qidirilmoqda..." xabarini o'chirish

        prompt = (
            f"Foydalanuvchi savoli: {user_text}"
            f"{context_text}"
            "\n\nAgar yuqorida internet ma'lumotlari bo'lsa, ulardan foydalanib eng so'nggi va aniq javobni o'zbek tilida ber."
            "Javobing samimiy va professional bo'lsin."
        )

        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        await update.message.reply_text(response.text)

    except Exception as e:
        logger.error(f"Matn xatosi: {e}")
        await update.message.reply_text("Xabarni qayta ishlashda xatolik yuz berdi.")

# ==============================
# 6️⃣ BOTNI ISHGA TUSHIRISH (MAIN)
# ==============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # CRITICAL TARTIB: Avval komandalar, keyin multimodal filtrlar, eng oxirida umumiy matn!
    app.add_handler(CommandHandler("start", start_handler))
    
    app.add_handler(CallbackQueryHandler(button_callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    app.add_handler(MessageHandler(filters.Document.PDF, analyze_pdf))
    app.add_handler(MessageHandler(filters.VOICE, analyze_voice))
    
    # Umumiy matn handlerini eng oxiriga qo'yamiz, aks holda u hamma narsani bloklaydi
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))

    print("🤖 Bot muvaffaqiyatli ishga tushdi (Polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
