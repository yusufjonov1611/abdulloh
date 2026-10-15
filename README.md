# 📚 Kitob Qidiruvchi Telegram Bot (PDF Search & Highlight Bot)

Ushbu bot PDF formatdagi kitob ichidan foydalanuvchi kiritgan har qanday so'z yoki iborani qidirib topadi, sahifasini aniqlaydi, qatordagi kontekstni ko'rsatadi, sahifani **rasm (skrinshot) qilib va o'sha so'zni sariq marker bilan belgilab** foydalanuvchiga taqdim etadi hamda elektron PDFda o'sha sahifani brauzerda ochish havolasini beradi.

---

## 🌟 Asosiy Imkoniyatlari

1. **Aqlli qidiruv:** Kitobning barcha sahifalaridan so'zni soniyalar ichida qidiradi.
2. **Vizual izoh (Rasm):** Qidirilgan so'z kitobning qaysi joyida kelganini ko'rsatish uchun sahifani rasmga aylantirib, so'z ustini sariq rang bilan belgilab (highlight) yuboradi.
3. **Sahifa va Qator ko'rinishi:** Qaysi sahifada va qaysi qatorda ishlatilganini aniq ko'rsatadi.
4. **Elektron variant havolasi (Deep Link):** Har bir natijada `https://sizning-domen/book#page=X` havolasi beriladi — uni bosgan foydalanuvchida PDF brauzerda to'g'ridan-to'g'ri o'sha sahifaga ochiladi.
5. **PDF faylni yuklab olish:** Bot orqali butun kitobni Telegramdan yuklab olish imkoniyati.
6. **Admin orqali yangilash:** Botga Telegram orqali yangi PDF kitob yuborilsa, u avtomatik yangilanadi.
7. **24/7 Bepul Server (Render.com):** Render.com da bepul Web Service sifatida doimiy ishlab turishi uchun yengil aiohttp server va keep-alive pinger bilan jihozlangan.

---

## 📁 Loyiha Strukturasi

```text
kitobbot/
│
├── bot.py             # Asosiy Telegram bot kodi va Render keep-alive
├── pdf_searcher.py    # PDF ichidan so'z qidirish va rasmga highlight qilish moduli
├── web_server.py      # Render.com portini ushlab turuvchi va PDFni ulashuvchi web server
├── requirements.txt   # Kerakli Python kutubxonalari
├── Procfile           # Render/Heroku ishga tushirish buyrug'i
├── render.yaml        # Render.com 1-bosqichli avtomatik sozlama
├── .env               # Token va sozlamalar fayli
└── books/             # Kitob fayllari (book.pdf)
```

---

## ⚙️ Sozlamalar (.env)

`kitobbot` papkasi ichidagi `.env` faylini ochib, quyidagilarni kiriting:

```env
BOT_TOKEN=bu_yerga_botfather_tokeni
APP_URL=https://sizning-loyiha.onrender.com
ADMIN_ID=123456789
PORT=10000
BOOK_PATH=books/book.pdf
```

- **`BOT_TOKEN`**: @BotFather dan olingan bot tokeni.
- **`ADMIN_ID`**: O'zingizning Telegram raqamli ID raqamingiz (@userinfobot orqali bilib olishingiz mumkin).
- **`APP_URL`**: Render.com ga joylagandan so'ng beriladigan manzil (masalan, `https://kitob-bot.onrender.com`).

---

## 🚀 Render.com ga Bepul va 24/7 Joylash Bo'yicha Qo'llanma

### 1-qadam: GitHub ga yuklash
1. [GitHub.com](https://github.com) saytida yangi repozitoriy (Repository) oching (masalan, `kitob-bot`).
2. `kitobbot` papkasidagi fayllarni GitHub ga yuklang (Push qiling).
   > **Maslahat:** Kitob hajmi 50-100 MB dan oshmasa, `books/book.pdf` faylini ham birga qo'shib yuklashingiz mumkin.

### 2-qadam: Render.com da yangi Web Service ochish
1. [Render.com](https://render.com) ga kiring va GitHub orqali ro'yxatdan o'ting.
2. **New +** tugmasini bosing va **Web Service** ni tanlang.
3. GitHub repozitoriyangizni ulang (`Connect`).
4. Quyidagi parametrlarni to'ldiring:
   - **Name:** `kitob-bot` (yoki istalgan nom)
   - **Language:** `Python`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Instance Type:** `Free`
5. Sahifaning pastrog'idagi **Environment Variables** bo'limida qo'shing:
   - `BOT_TOKEN` = Sizning bot tokeningiz
   - `ADMIN_ID` = Sizning Telegram ID raqamingiz
   - `APP_URL` = Render beradigan domen manzili (Deploy tugagandan keyin olinadi)
6. **Create Web Service** tugmasini bosing. Render loyihangizni bir necha daqiqada ishga tushiradi!

---

## ⏰ Bot 24/7 Uxlab Qolmasdan Ishlashi Uchun (UptimeRobot)

Render.com ning bepul tarifi 15 daqiqa murojaat bo'lmasa "uxlab qoladi" (sleep mode).
Buning oldini olish juda oson:

1. [UptimeRobot.com](https://uptimerobot.com) saytiga bepul kiring (ro'yxatdan o'ting).
2. **Add New Monitor** tugmasini bosing:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `Kitob Bot`
   - **URL (or IP):** `https://sizning-botingiz.onrender.com/health`
   - **Monitoring Interval:** Har `10 minutes` (10 daqiqa)
3. **Create Monitor** tugmasini bosing.
Endi UptimeRobot har 10 daqiqada botingizga signal yuborib turadi va bot Render.com da 24/7 uzluksiz ishlab turadi!

---

## 📖 Botdan Foydalanish

1. Telegramda botingizga `/start` buyrug'ini yuborasiz.
2. Agar botga kitob hali joylanmagan bo'lsa, adminga havola qilinadi — admin botga to'g'ridan-to'g'ri PDF fayl yuborishi kifoya, bot uni avtomatik qabul qilib saqlaydi!
3. Kitob ichidan qidirmoqchi bo'lgan so'zni yozing (masalan, *Bobur*, *ilm*, *quyosh*).
4. Bot darhol o'sha so'z uchragan sahifalarni, qator matnini, sahifani sariq marker bilan belgilangan rasm holatida va elektron nusxadagi sahifani ochish havolasini chiqarib beradi!
