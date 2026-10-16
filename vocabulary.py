# -*- coding: utf-8 -*-
"""
Kitobdagi barcha so'zlarning asl ma'nolari (qomusiy ta'riflari)
va kitobdagi gaplarning o'zbekcha mazmunini aniqlash moduli.
Inglizcha va o'zbekcha qomusiy ta'riflarni aniq taqdim etadi.
"""

import urllib.request
import urllib.parse
import json
from functools import lru_cache

# Asosiy yuridik va ilmiy terminlarning professional qomusiy lug'ati
VOCABULARY_DEFINITIONS = {
    "judge": {
        "meaning_uz": "Sudya — sud majlislarida ishlarni ko'rib chiquvchi, dalillarni baholovchi va yakuniy qonuniy qaror (hukm) chiqaruvchi mansabdor shaxs.",
        "meaning_en": "A public official appointed to hear and decide legal cases in a court of law."
    },
    "lawyer": {
        "meaning_uz": "Huquqshunos / Advokat — qonunlar bo'yicha maxsus ma'lumotga ega bo'lgan va mijozlarga yuridik maslahat hamda sudda himoya beruvchi mutaxassis.",
        "meaning_en": "A person who is qualified to advise people about the law and to represent them in court."
    },
    "solicitor": {
        "meaning_uz": "Solitsitor — Angliyada mijozlarga to'g'ridan-to'g'ri maslahat beruvchi, hujjatlar tayyorlovchi va quyi sudlarda ish olib boruvchi yurist.",
        "meaning_en": "In the UK, a lawyer who gives legal advice, prepares legal documents, and represents clients in lower courts."
    },
    "barrister": {
        "meaning_uz": "Barristor — Angliyada asosan yuqori sudlarda sudlov ishlarida qatnashish (advocacy) va sudda nutq so'zlashga ixtisoslashgan advokat.",
        "meaning_en": "In the UK, a lawyer who is qualified to represent clients in higher courts of law."
    },
    "attorney": {
        "meaning_uz": "Advokat / Ishonchli vakil — AQSHda huquqshunos (advokat) deb yuritiladi; boshqa shaxs nomidan ish ko'rish huquqiga ega yurist.",
        "meaning_en": "A person legally appointed to act on behalf of another; in the US, a lawyer."
    },
    "court": {
        "meaning_uz": "Sud — odil sudlovni amalga oshiruvchi, fuqarolik, jinoiy va ma'muriy ishlarni qonun asosida hal qiluvchi davlat organi.",
        "meaning_en": "A place or judicial assembly where legal trials and justice take place."
    },
    "contract": {
        "meaning_uz": "Shartnoma — ikki yoki undan ortiq tomon o'rtasida qonuniy majburiyatlarni vujudga keltiruvchi rasmiy kelishuv.",
        "meaning_en": "A legally binding agreement between two or more parties."
    },
    "litigation": {
        "meaning_uz": "Sud jarayoni / Sudlashuv — nizolarni sud orqali da'vo arizasi kiritish va ko'rib chiqish yo'li bilan hal qilish jarayoni.",
        "meaning_en": "The process of taking legal action or a lawsuit in a court of law."
    },
    "advocacy": {
        "meaning_uz": "Himoyachilik mahorati — sudda mijoz manfaatlarini himoya qilib professional nutq so'zlash va dalillarni taqdim etish san'ati.",
        "meaning_en": "The skill or activity of speaking and pleading for someone in a court of law."
    },
    "client": {
        "meaning_uz": "Mijoz — advokat yoki yuridik firmaning xizmatidan foydalanuvchi shaxs yoki kompaniya.",
        "meaning_en": "A person or organization using the services of a lawyer or professional firm."
    },
    "partnership": {
        "meaning_uz": "Sheriklik / Hamkorlik — ikki yoki undan ortiq yuristlar birgalikda yuridik amaliyot (firma) yuritish shakli.",
        "meaning_en": "A legal business entity where two or more persons share management and profits."
    },
    "claim": {
        "meaning_uz": "Da'vo / Talab — biror shaxs yoki tashkilotdan huquqiy majburiyat yoki tovon pulini talab qilib sudga murojaat qilish.",
        "meaning_en": "A formal demand for something that is believed to be legally due."
    },
    "claimant": {
        "meaning_uz": "Da'vogar — sudda o'z huquqlari buzilganini aytib, qarshi tomonga nisbatan da'vo kiritgan shaxs.",
        "meaning_en": "A person who makes a formal claim in a civil court."
    },
    "defendant": {
        "meaning_uz": "Javobgar / Sudlanuvchi — sudda o'ziga nisbatan da'vo qo'zg'atilgan yoki ayblanayotgan tomon.",
        "meaning_en": "A person or company against whom a claim or criminal charge is brought in court."
    },
    "dispute": {
        "meaning_uz": "Nizo / Bahs — ikki yoki undan ortiq tomon o'rtasidagi qonuniy huquq yoki majburiyatlar yuzasidan kelib chiqqan ixtilof.",
        "meaning_en": "A disagreement or argument between parties, especially one resulting in legal proceedings."
    },
    "pleading": {
        "meaning_uz": "Ishni himoya qilish — sudda o'z dalillari va pozitsiyasini himoya qilib ko'rsatma berish.",
        "meaning_en": "The formal statement of the cause of an action or defence in court."
    },
    "qualified": {
        "meaning_uz": "Malakali / Litsenziyaga ega — maxsus imtihonlarni topshirib, kasbiy faoliyat bilan qonuniy shug'ullanish huquqini olgan.",
        "meaning_en": "Having finished required training or passed exams to practice a profession legally."
    },
    "specialise": {
        "meaning_uz": "Ixtisoslashmoq — huquqning ma'lum bir sohasiga (masalan, tijorat huquqi, jinoyat huquqi) chuqur ixtisoslashish.",
        "meaning_en": "To concentrate on and become an expert in a particular subject or legal skill."
    },
    "law firm": {
        "meaning_uz": "Yuridik firma — advokatlar va yuristlar jamoasi tomonidan mijozlarga huquqiy xizmat ko'rsatadigan kompaniya.",
        "meaning_en": "A business partnership formed by lawyers to engage in the practice of law."
    },
    "bailiff": {
        "meaning_uz": "Sud ijrochisi — sud qarorlarining ijrosini ta'minlovchi, to'lanmagan qarzlarni undiruvchi mansabdor shaxs.",
        "meaning_en": "An official who keeps order in court and enforces court orders and seizures of property."
    },
    "tort": {
        "meaning_uz": "Fuqarolik huquqbuzarligi (Deliqt) — shaxsga yoki mol-mulkka yetkazilgan noqonuniy zarar tufayli yuzaga keladigan huquqiy javobgarlik.",
        "meaning_en": "A civil wrong or injury (other than breach of contract) for which court provides a remedy."
    },
    "damages": {
        "meaning_uz": "Kompensatsiya / Zararni qoplash — yetkazilgan zarar evaziga sud tomonidan belgilanadigan pul to'lovi.",
        "meaning_en": "A sum of money claimed or awarded in compensation for a loss or injury."
    },
    "liability": {
        "meaning_uz": "Huquqiy javobgarlik — qonun bo'yicha majburiyat yoki zararni qoplash mas'uliyati.",
        "meaning_en": "The state of being legally responsible for something."
    },
    "negligence": {
        "meaning_uz": "Ehtiyotsizlik / Parvosizlik — belgilangan ehtiyotkorlik qoidalariga rioya qilmaslik oqibatida zarar yetkazish.",
        "meaning_en": "Failure to take proper care over something, resulting in damage or injury to another."
    },
    "breach": {
        "meaning_uz": "Buzish — qonuniy majburiyat yoki shartnoma shartlarini buzish.",
        "meaning_en": "An act of breaking or failing to observe a law, agreement, or code of conduct."
    },
    "breach of contract": {
        "meaning_uz": "Shartnomani buzish — shartnomada belgilangan majburiyatlarni bajarmaslik yoki lozim darajada bajarmaslik.",
        "meaning_en": "A failure, without legal excuse, to perform any promise that forms all or part of a contract."
    },
    "obligation": {
        "meaning_uz": "Majburiyat — qonun yoki shartnoma talabiga binoan biror harakatni amalga oshirish yoki undan tiyilish burchi.",
        "meaning_en": "A legal or moral duty that an individual is bound to perform."
    },
    "agreement": {
        "meaning_uz": "Kelishuv / Bitim — ikki yoki undan ortiq shaxslarning birgalikdagi huquq va majburiyatlar bo'yicha mushtarak irodasi.",
        "meaning_en": "A negotiated and usually legally enforceable understanding between two or more parties."
    },
    "remedy": {
        "meaning_uz": "Huquqiy himoya vositasi — huquqi buzilgan shaxsga sud tomonidan beriladigan tovon yoki chora (masalan, zararni qoplash, taqiq qo'yish).",
        "meaning_en": "The means with which a court of law enforces a right, imposes a penalty, or makes another court order to impose its will."
    },
    "injunction": {
        "meaning_uz": "Sud taqiqi (Injunction) — sud tomonidan ma'lum bir harakatni bajarishni taqiqlovchi yoki majburlovchi rasmiy farmoyish.",
        "meaning_en": "An authoritative judicial warning or order restraining a person from beginning or continuing an action."
    }
}

@lru_cache(maxsize=1500)
def translate_sentence_to_uzbek(sentence: str) -> str:
    """
    Kitobdagi gapning o'zbekcha aniq kontekstdagi tarjimasi va mazmunini qaytaradi.
    """
    s = sentence.strip()
    if not s:
        return ""
    url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=uz&dt=t&q=' + urllib.parse.quote(s)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            translated = "".join([item[0] for item in data[0] if item and item[0]])
            return translated.strip()
    except Exception:
        return ""

@lru_cache(maxsize=1000)
def fetch_online_word_definition(word: str) -> dict:
    """
    Istalgan so'z yoki iboraning inglizcha va o'zbekcha asl qomusiy ma'nosini
    aniq, ketma-ket va tushunarli qilib oladi.
    """
    w = word.strip().lower()
    if not w:
        return None

    # 1. O'zbekcha ma'nosi va so'z turkumlari
    meaning_uz = ""
    url_uz = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=uz&dt=t&dt=bd&q=' + urllib.parse.quote(w)
    req_uz = urllib.request.Request(url_uz, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req_uz, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            primary = data[0][0][0].strip().capitalize() if data and data[0] else ""
            parts = []
            if len(data) > 1 and data[1]:
                for group in data[1]:
                    pos = group[0]  # noun, verb, adjective
                    items = group[1][:3]
                    parts.append(pos + ": " + ", ".join(items))
            if parts:
                meaning_uz = primary + " (" + "; ".join(parts) + ")"
            else:
                meaning_uz = primary
    except Exception:
        meaning_uz = word.capitalize()

    # 2. Inglizcha qomusiy ta'rifi (English Definition)
    meaning_en = ""
    url_en = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=en&dt=md&dt=t&q=' + urllib.parse.quote(w)
    req_en = urllib.request.Request(url_en, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req_en, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if len(data) > 12 and data[12]:
                defs = []
                for entry in data[12]:
                    pos = entry[0]
                    for d in entry[1][:1]:
                        defs.append(f"({pos}) {d[0]}")
                meaning_en = " ".join(defs)
    except Exception:
        meaning_en = ""

    return {
        "meaning_uz": meaning_uz or word.capitalize(),
        "meaning_en": meaning_en
    }

def get_word_definition(word: str) -> dict:
    """
    So'zning asl qomusiy ma'nosini qaytaradi (Inglizcha va O'zbekcha).
    Avval professional yuridik bazadan qidiradi, bo'lmasa to'liq onlayn ta'rif oladi.
    """
    if not word:
        return None
    w = word.strip().lower()

    # 1. Aniq moslik bazada
    if w in VOCABULARY_DEFINITIONS:
        return VOCABULARY_DEFINITIONS[w]

    # 2. Zamon / ko'plik qo'shimchalari bo'yicha bazadan tekshirish
    stems = []
    if w.endswith("ies") and len(w) > 4: stems.append(w[:-3] + "y")
    if w.endswith("es") and len(w) > 3: stems.extend([w[:-2], w[:-1]])
    if w.endswith("s") and len(w) > 3: stems.append(w[:-1])
    if w.endswith("ed") and len(w) > 3: stems.extend([w[:-2], w[:-1]])
    if w.endswith("ing") and len(w) > 4: stems.extend([w[:-3], w[:-3] + "e"])

    for s in stems:
        if s in VOCABULARY_DEFINITIONS:
            base_def = VOCABULARY_DEFINITIONS[s]
            return {
                "meaning_uz": f"{base_def['meaning_uz']}",
                "meaning_en": f"Form of '{s}': {base_def['meaning_en']}"
            }

    # 3. Istalgan so'z uchun to'liq onlayn qomusiy ta'rif
    return fetch_online_word_definition(w)
