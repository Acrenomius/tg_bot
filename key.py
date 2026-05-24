import os
import logging
import traceback
from dotenv import load_dotenv

# Yangi rasmiy Google SDK (Gemini 2.5 uchun)
from google import genai
from google.genai import types

# PDF va Bepul Internet qidiruv kutubxonalari
import fitz  # PyMuPDF
from duckduckgo_search import DDGS

# Telegram Bot API kutubxonalari
from telegram import Update, constants
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters
)

# ==============================
# 1️⃣ SOZLAMALAR
# ==============================
load_dotenv()
TOKEN = "8559822278:AAFjJK95n-xQAezOz0hTPEgZPyYCRB6zlpI"  # <-- O'zingizning haqiqiy tokeningizni yozing

# ✅ YANGI TO'G'RI VARIANT: 
# Railway'dagi 'Variables' bo'limiga GEMINI_API_KEY kalitini qo'shishni unutmang!
client = genai.Client(api_key="AIzaSyBYrXFC_BDDFmnSILE-cd98eXXdZVbRL5Y")
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ==============================
# 2️⃣ PDF TAHLILI FUNKSIYASI
# ==============================
async def analyze_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.document.get_file()
    
    if not update.message.document.file_name.lower().endswith('.pdf'):
        return

    await update.message.reply_text("PDF qabul qilindi. Matn o'qilmoqda... 📄")

    try:
        pdf_bytes = await file.download_as_bytearray()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        full_text = ""
        for page in doc:
            full_text += page.get_text()
        doc.close()

        # Matn borligini tekshiramiz
        clean_text = full_text.strip()
        
        if len(clean_text) > 10:
            await update.message.reply_text("Hujjat tahlil qilinmoqda... ✨")
            
            prompt = (
                "Quyidagi PDF hujjat matnini diqqat bilan tahlil qil va uning eng muhim qismlarini "
                "chiroyli tarzda va foydalanuvchi tushunadigan tarzda yetkaz. Foydalanuvchi huddi kitoobni oqigandek bolsin, shunday yetkazginki. "
                "Kitob ichidagi eng oqilganda eng yorqin bolgan matnlarni tushuntirganingdan keyin, yozib qoy. "
                "Ortiqcha belgilarga e'tibor qaratma va ozing ham bu belgilarni ishlatma. Qora shriftdagi harflar kerak emas. "
                "Foydalauvchi uzun matnlarni yomon koradi. Qora harf vaa so'zlardan foydalanma. Context kerak emas. Xulosa ham. "
                "HECH QANDAY sarlavha, kirish so'zi (masalan: 'Hujjat mazmuni', 'Mana tahlil') yozma! "
                f"\n\nMatn: {clean_text[:15000]}"
            )
            
            # ✅ Yangi SDK sintaksisiga o'tkazildi
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            
            # 1. Avval natijani olamiz
            final_output = response.text.strip() if response.text else ""
            
            # 2. Sarlavhalarni dasturiy tozalash (Filtr)
            filter_words = ["Hujjatning qisqacha mazmuni:", "Hujjat mazmuni:", "Tahlil:", "**Hujjatning qisqacha mazmuni:**"]
            for word in filter_words:
                if final_output.startswith(word):
                    final_output = final_output.replace(word, "", 1).strip()

            # 3. Faqat endi javobni yuboramiz
            if final_output:
                await update.message.reply_text(final_output)
            else:
                await update.message.reply_text("Tahlil natijasini olishda muammo bo'ldi.")
            
        else:
            await update.message.reply_text("PDF ichida o'qish uchun matn topilmadi.")

    except Exception as e:
        print(f"Xato yuz berdi: {e}")
        await update.message.reply_text("PDF tahlilida texnik xatolik yuz berdi.")

# ==============================
# 3️⃣ MATN VA RASM FUNKSIYALARI
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
       "✨ *Assalomu alaykum!* ✨\n\n"
        "Botimizga xush kelibsiz.\n\n"
        "❓ Bot bo'yicha savollaringiz bo'lsa:\n"
        "➖➖➖➖➖➖➖➖➖➖\n"
        "👨‍💻 @acrenomius\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def analyze_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytearray = await photo_file.download_as_bytearray()
        await update.message.reply_text("Rasm o'qilmoqda... 🔍")

        # Yangi SDK formatida rasm partiyasini tayyorlash
        image_part = types.Part.from_bytes(
            data=bytes(image_bytearray),
            mime_type="image/jpeg"
        )
        
        prompt = (
            "Rasmdagi matnni o'zbek tiliga tarjima qil. "
            "So'zlarni shunchaki tarjima qilma, umumiy ma'nosini yetkaz. "
            "qora harflarni ishlatma. Agar rasmda ajratilgan biror belgi bolsa oshani qoyishing mumkin. "
            "Sen ozing ortiqcha deb belgilagan yoki rasmda ortiqchadek tuyulgan belgilar shartmas"
        )
        
        # ✅ Yangi SDK sintaksisiga o'tkazildi
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, image_part]
        )
        await update.message.reply_text(response.text if response.text else "Matn topilmadi.")
    except Exception as e:
        await update.message.reply_text(f"Rasm xatosi: {str(e)}")

async def analyze_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Ovozli xabar eshitilmoqda... 🎧")
    
    try:
        voice_file = await update.message.voice.get_file()
        voice_bytearray = await voice_file.download_as_bytearray()
        
        # Yangi SDK formatida audio partiyasini tayyorlash
        audio_part = types.Part.from_bytes(
            data=bytes(voice_bytearray),
            mime_type="audio/ogg"
        )
        
        prompt = (
            "Ushbu audio xabarni tingla va o'zbek tilida mantiqiy javob ber. "
            "Agar savol bo'lsa javob qaytar, agar shunchaki fikr bo'lsa unga munosabat bildir. "
            "Javobing samimiy va tushunarli bo'lsin."
        )
        
        # ✅ Yangi SDK sintaksisiga o'tkazildi
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, audio_part]
        )
        
        if response.text:
            await update.message.reply_text(f"🎤 **Javob:**\n\n{response.text}")
        else:
            await update.message.reply_text("Ovozni tushunib bo'lmadi, qaytadan yozib ko'ring.")

    except Exception as e:
        print(f"Ovoz xatosi: {e}")
        await update.message.reply_text("Ovozli xabarni tahlil qilishda texnik xatolik yuz berdi. ✨")

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
        print(f"Qidiruv xatosi: {e}")
        return None
    
# --- MATN TAHLILI ---
async def analyze_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    
    trigger_words = ["top", "qidir", "search", "yangilik", "kursi", "ob-havo"]
    use_internet = any(word in user_text.lower() for word in trigger_words)

    try:
        context_text = ""
        
        if use_internet:
            await update.message.reply_text("🌐 Internetdan qidirilmoqda...")
            search_data = search_internet(user_text)
            if search_data:
                context_text = f"\n\nInternetdan topilgan ma'lumotlar:\n{search_data}"

        prompt = (
            f"Foydalanuvchi savoli: {user_text}"
            f"{context_text}"
            "\n\nAgar yuqorida internet ma'lumotlari bo'lsa, ulardan foydalanib eng so'nggi va aniq javobni o'zbek tilida ber."
            "Javobing samimiy va professional bo'lsin."
        )

        # ✅ Yangi SDK sintaksisiga o'tkazildi
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        await update.message.reply_text(response.text)

    except Exception as e:
        print(f"Xato: {e}")
        await update.message.reply_text(f"Xatolik: {str(e)}")


# --- MP3 TRANSLATION HANDLER (TUZATILDI) ---
async def mp3_translation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Vaqtincha fayl nomi
    temp_file_path = f"temp_audio_{update.message.message_id}.mp3"
    uploaded_file = None
    
    try:
        # 1. Foydalanuvchiga jarayon boshlanganini bildirish
        waiting_message = await update.message.reply_text(
            "⏳ <b>MP3 audio fayl qabul qilindi.</b> Tizim tovush to'lqinlarini tahlil qilmoqda, iltimos kuting...",
            parse_mode="HTML"
        )

        # 2. Telegramdan faylni yuklab olish va server diskiga vaqtincha yozish
        audio_file = await update.message.audio.get_file()
        await audio_file.download_to_drive(custom_path=temp_file_path)

        # 3. KAFOLATLANGAN USUL: Faylni to'g'ridan-to'g'ri Google File API orqali yuklaymiz
        # Bu usulda baytlar bilan ishlashdagi asinxron xatoliklar (httpx timeout) mutloq yuz bermaydi
        uploaded_file = client.files.upload(
            file=temp_file_path,
            config=types.UploadFileConfig(mime_type="audio/mp3")
        )

        prompt = (
            "Ushbu audio faylni diqqat bilan tingla. Undagi nutq qaysi tilda bo'lishidan qat'iy nazar "
            "gapirilgan gaplarni aniq tushunib, mazmunini zarracha buzmagan holda "
            "akademik va tushunarli o'zbek tiliga tarjima qilib ber. Faqat tarjima matnini qaytar, "
            "ortiqcha izoh yoki 'mana tarjima' kabi kirish so'zlarini mutloq yozma."
        )

        # 4. Modelga fayl obyekti va promptni yuboramiz
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[uploaded_file, prompt]
        )

        # 5. Kutish xabarini o'chirish
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=waiting_message.message_id)
        
        if response.text:
            await update.message.reply_text(
                f"🇺🇿 <b>Audio faylning o'zbekcha tarjimasi:</b>\n\n{response.text}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text("❌ Audio fayldan nutqni ajratib olishda model xatolikka uchradi.")

    except Exception as e:
        logging.error(f"MP3 Tarjima Xatosi: {traceback.format_exc()}")
        await update.message.reply_text("❌ Audio faylni qayta ishlashda kutilmagan texnik xatolik yuz berdi.")
        
    finally:
        # 6. TOZALASH: Vaqtincha fayllarni o'chiramiz (Server xotirasi to'lib qolmasligi uchun)
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except Exception:
                pass
                
        # Google bulutidan ham vaqtincha faylni o'chirish
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
    
# ==============================
# 4️⃣ BOTNI ISHGA TUSHIRISH
# ==============================
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # Handlerlarni tartib bilan qo'shish
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_text))
    app.add_handler(MessageHandler(filters.PHOTO, analyze_image))
    app.add_handler(MessageHandler(filters.Document.PDF, analyze_pdf))
    app.add_handler(MessageHandler(filters.VOICE, analyze_voice))
    app.add_handler(MessageHandler(filters.AUDIO, mp3_translation_handler))

    print("🤖 Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()
