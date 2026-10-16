import pymupdf
import io
import re
import unicodedata
from typing import List, Dict, Any, Optional
from vocabulary import get_word_definition

def normalize_text(text: str) -> str:
    """
    Matndagi barcha maxsus belgilar, apostroflar, tirelar va
    bo'shliqlarni standart holatga keltiradi.
    """
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', text)
    # Satr oxirida chiziqcha bilan bo'lingan so'zlarni birlashtirish (dehyphenate)
    text = re.sub(r'(\w+)-\s*\n\s*(\w+)', r'\1\2', text)
    replacements = {
        '’': "'", '‘': "'", '`': "'", '“': '"', '”': '"',
        '–': '-', '—': '-', '−': '-',
        '\xa0': ' ', '\u200b': '', '\u200e': '', '\u200f': '',
        '…': '...', '\t': ' ', '\r': ' ', '\n': ' '
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return " ".join(text.split())

def clean_search_query(query: str) -> str:
    """
    Qidiruv so'zini tozalaydi (chetki nuqta, vergul, qavslar va tirnoqlarni olib tashlaydi).
    """
    if not query:
        return ""
    q = normalize_text(query)
    q = q.strip('.,;:?!"\'()[]{}«»“”‘’<> \t\r\n')
    return q

def generate_word_variants(query: str) -> List[str]:
    """
    So'zning boshqa zamon, ko'plik/birlik va asosiy shakllarini hosil qiladi.
    """
    w = clean_search_query(query).lower()
    variants = []

    def add_var(v: str):
        v = clean_search_query(v).lower()
        if len(v) >= 3 and v not in variants and v != w:
            variants.append(v)

    if " " in w or len(w) < 3:
        return [w]

    # 1. Ko'plik / Birlik (Plural / Singular)
    if w.endswith("ies") and len(w) > 4:
        add_var(w[:-3] + "y")
    elif w.endswith("es") and len(w) > 3:
        add_var(w[:-1])
        add_var(w[:-2])
    elif w.endswith("s") and len(w) > 3:
        add_var(w[:-1])
    else:
        add_var(w + "s")
        if w.endswith(("s", "x", "z", "ch", "sh")):
            add_var(w + "es")
        if w.endswith("y") and len(w) > 3 and w[-2] not in "aeiou":
            add_var(w[:-1] + "ies")

    # 2. Fe'l zamonlari (-ing, -ed, -d)
    if w.endswith("ing") and len(w) > 4:
        stem = w[:-3]
        add_var(stem + "e")  # judging -> judge, practising -> practise
        add_var(stem)        # training -> train, hearing -> hear
        if len(stem) > 2 and stem[-1] == stem[-2]:
            add_var(stem[:-1])  # running -> run
    elif w.endswith("ed") and len(w) > 3:
        stem = w[:-2]
        add_var(w[:-1])      # judged -> judge, practised -> practise
        add_var(stem)        # trained -> train
        if w.endswith("ied") and len(w) > 4:
            add_var(w[:-3] + "y")
    else:
        if w.endswith("e"):
            add_var(w + "d")
            add_var(w[:-1] + "ing")
            add_var(w + "s")
        else:
            add_var(w + "ed")
            add_var(w + "ing")

    # 3. Noto'g'ri fe'llar (Irregular verbs)
    irregulars = {
        "go": ["went", "gone", "going", "goes"],
        "see": ["saw", "seen", "seeing", "sees"],
        "write": ["wrote", "written", "writing", "writes"],
        "give": ["gave", "given", "giving", "gives"],
        "take": ["took", "taken", "taking", "takes"],
        "speak": ["spoke", "spoken", "speaking", "speaks"],
        "know": ["knew", "known", "knowing", "knows"],
        "run": ["ran", "running", "runs"],
        "pay": ["paid", "paying", "pays"],
        "think": ["thought", "thinking", "thinks"],
        "bring": ["brought", "bringing", "brings"],
        "buy": ["bought", "buying", "buys"],
        "make": ["made", "making", "makes"],
        "find": ["found", "finding", "finds"],
        "hear": ["heard", "hearing", "hears"],
        "read": ["reading", "reads"],
        "lead": ["led", "leading", "leads"],
        "choose": ["chose", "chosen", "choosing", "chooses"]
    }
    for base, forms in irregulars.items():
        if w == base or w in forms:
            add_var(base)
            for f in forms:
                add_var(f)

    return [w] + variants

def extract_best_sentence(block_text: str, query: str) -> str:
    """
    Qidirilgan so'z qatnashgan eng to'liq va mazmunli gapni ajratib beradi.
    """
    clean_block = normalize_text(block_text)
    if not clean_block:
        return ""

    # Gap chegaralari bo'yicha ajratish
    sentences = re.split(r'(?<=[.!?])\s+', clean_block)
    matched_sentences = []
    q_lower = query.lower()

    for s in sentences:
        if q_lower in s.lower():
            s_clean = s.strip()
            if s_clean and s_clean not in matched_sentences:
                matched_sentences.append(s_clean)

    if matched_sentences:
        res = " ".join(matched_sentences)
        # Agar gap juda qisqa bo'lsa (masalan, lug'at ro'yxatida) to'liq blokni qaytaramiz
        if len(res.split()) < 7 and len(clean_block.split()) <= 45:
            return clean_block
        return res

    return clean_block

def _search_single_term(doc, term: str, max_results: int = 6) -> Dict[str, Any]:
    """
    Normalizatsiya qilingan term bo'yicha barcha sahifalardan bloklar va matnlarni qidiradi.
    """
    total_occurrences = 0
    results: List[Dict[str, Any]] = []
    seen_texts = set()

    clean_term = clean_search_query(term)
    if not clean_term:
        return {"total": 0, "results": []}

    is_single_word = (" " not in clean_term)
    word_pattern = None
    if is_single_word and clean_term.isalnum():
        word_pattern = re.compile(r'\b' + re.escape(clean_term) + r'\b', re.IGNORECASE)

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_num = page_index + 1

        blocks = page.get_text("blocks")
        page_matched = False

        for b in blocks:
            b_text = b[4]
            norm_b = normalize_text(b_text)
            if not norm_b:
                continue

            matches_in_block = 0
            if word_pattern:
                m_list = word_pattern.findall(norm_b)
                matches_in_block = len(m_list)
            else:
                if clean_term.lower() in norm_b.lower():
                    matches_in_block = norm_b.lower().count(clean_term.lower())

            if matches_in_block > 0:
                total_occurrences += matches_in_block
                page_matched = True

                sentence = extract_best_sentence(norm_b, clean_term)
                key = (page_num, sentence)
                if key not in seen_texts:
                    seen_texts.add(key)
                    if len(results) < max_results:
                        results.append({
                            "page": page_num,
                            "sentence": sentence
                        })

        # Agar bloklarda topilmasa, lekin butun sahifa matnida (bloklararo) bo'lishi mumkin
        if not page_matched:
            norm_page = normalize_text(page.get_text("text"))
            found_on_page = False
            if word_pattern:
                m_list = word_pattern.findall(norm_page)
                if m_list:
                    total_occurrences += len(m_list)
                    found_on_page = True
            else:
                if clean_term.lower() in norm_page.lower():
                    total_occurrences += norm_page.lower().count(clean_term.lower())
                    found_on_page = True

            if found_on_page:
                sentence = extract_best_sentence(norm_page, clean_term)
                key = (page_num, sentence)
                if key not in seen_texts:
                    seen_texts.add(key)
                    if len(results) < max_results:
                        results.append({
                            "page": page_num,
                            "sentence": sentence
                        })

    return {
        "total": total_occurrences,
        "results": results
    }

def search_word_in_pdf(
    pdf_path: str,
    query: str,
    max_results: int = 6
) -> Dict[str, Any]:
    """
    Berilgan so'z yoki iborani PDF ichidan mukammal qidiradi.
    Sahifa raqami, kontekst iqtibosi va qomusiy ma'nosini qaytaradi.
    """
    clean_q = clean_search_query(query)
    if not clean_q:
        return {"total": 0, "results": [], "query": query, "matched_query": query, "definition": None}

    doc = pymupdf.open(pdf_path)

    # 1. To'g'ridan-to'g'ri qidiruv (aniq kiritilgan so'z yoki ibora)
    first_attempt = _search_single_term(doc, clean_q, max_results)
    if first_attempt["total"] > 0:
        doc.close()
        definition = get_word_definition(clean_q)
        return {
            "total": first_attempt["total"],
            "results": first_attempt["results"],
            "query": clean_q,
            "matched_query": clean_q,
            "definition": definition
        }

    # 2. Zamon va shakllari bo'yicha qidiruv (birlik, ko'plik, fe'l shakllari)
    variants = generate_word_variants(clean_q)
    for variant in variants[1:]:
        var_attempt = _search_single_term(doc, variant, max_results)
        if var_attempt["total"] > 0:
            doc.close()
            definition = get_word_definition(variant) or get_word_definition(clean_q)
            return {
                "total": var_attempt["total"],
                "results": var_attempt["results"],
                "query": clean_q,
                "matched_query": variant,
                "definition": definition
            }

    # 3. Agar ko'p so'zli jumla bo'lsa va to'liq topilmasa, qismlarini sinab ko'rish
    words = clean_q.split()
    if len(words) >= 4:
        for sub_len in [4, 3]:
            if len(words) >= sub_len:
                sub_phrase = " ".join(words[:sub_len])
                sub_attempt = _search_single_term(doc, sub_phrase, max_results)
                if sub_attempt["total"] > 0:
                    doc.close()
                    return {
                        "total": sub_attempt["total"],
                        "results": sub_attempt["results"],
                        "query": clean_q,
                        "matched_query": sub_phrase,
                        "definition": None
                    }

    doc.close()
    return {
        "total": 0,
        "results": [],
        "query": clean_q,
        "matched_query": clean_q,
        "definition": get_word_definition(clean_q)
    }

def get_total_pages(pdf_path: str) -> int:
    try:
        doc = pymupdf.open(pdf_path)
        pages = len(doc)
        doc.close()
        return pages
    except Exception:
        return 0
