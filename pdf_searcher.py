# -*- coding: utf-8 -*-
"""
PDF kitoblar ichidan so'z va iboralarni sun'iy intellekt (AI) va
morfologik tahlil asosida mukammal va tezkor qidiruv moduli.

Xususiyatlari:
1. Aniq moslik (Exact match).
2. Morfologik va grammatik tahlil (birlik/ko'plik, fe'l zamonlari: image <-> images, agree <-> agreement).
3. Noaniq va imlo xatolarini tuzatish (Fuzzy matching / Levenshtein).
4. Bir martalik tezkor guruhli tarjima (Batch translation) — qidiruv 1-2 soniyada chiqadi.
"""

import pymupdf
import io
import re
import unicodedata
import difflib
import urllib.request
import urllib.parse
import json
from functools import lru_cache
from typing import List, Dict, Any, Optional, Set
from vocabulary import get_word_definition

def _batch_translate_sentences_to_uzbek(sentences: List[str]) -> List[str]:
    """
    Topilgan barcha gaplarni bitta tezkor so'rovda o'zbek tiliga tarjima qiladi (1-2 soniya).
    """
    if not sentences:
        return []

    # Bo'sh yoki juda qisqa bo'lmagan gaplar
    clean_sents = [s.strip() for s in sentences]
    if not any(clean_sents):
        return ["" for _ in sentences]

    delimiter = "\n<<==>>\n"
    combined = delimiter.join(clean_sents)

    url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=uz&dt=t&q=' + urllib.parse.quote(combined)
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            full_translated = "".join([item[0] for item in data[0] if item and item[0]])
            parts = full_translated.split("<<==>>")
            results = [p.strip() for p in parts]
            if len(results) == len(sentences):
                return results
            # Agar bo'linishda moslik bo'lmasa
            while len(results) < len(sentences):
                results.append("")
            return results[:len(sentences)]
    except Exception:
        # Fallback: agar internet xatosi bo'lsa
        return ["" for _ in sentences]

def _enrich_results_with_meaning(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Har bir topilgan gapning o'zbekcha mazmuni va tarjimasini tezkor qo'shadi.
    """
    sentences = [item.get("sentence", "") for item in results]
    meanings = _batch_translate_sentences_to_uzbek(sentences)
    for idx, item in enumerate(results):
        item["sentence_meaning"] = meanings[idx] if idx < len(meanings) else ""
    return results

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
    So'zning boshqa zamon, ko'plik/birlik, o'zak va derivatsion shakllarini hosil qiladi.
    Masalan:
    image -> images, imaging, imaged
    images -> image, imaging, imaged
    agree -> agreement, agreed, agreeing, agrees
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
        add_var(w[:-2])
        add_var(w[:-1])
    elif w.endswith("s") and len(w) > 3:
        add_var(w[:-1])
        if w.endswith("ss"):
            add_var(w)
    else:
        add_var(w + "s")
        if w.endswith(("s", "x", "z", "ch", "sh")):
            add_var(w + "es")
        if w.endswith("y") and len(w) > 3 and w[-2] not in "aeiou":
            add_var(w[:-1] + "ies")

    # 2. Fe'l zamonlari (-ing, -ed, -d)
    if w.endswith("ing") and len(w) > 4:
        stem = w[:-3]
        add_var(stem + "e")  # judging -> judge, imaging -> image
        add_var(stem)        # training -> train, hearing -> hear
        if len(stem) > 2 and stem[-1] == stem[-2]:
            add_var(stem[:-1])  # running -> run
    elif w.endswith("ed") and len(w) > 3:
        stem = w[:-2]
        add_var(w[:-1])      # judged -> judge, imaged -> image
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
            if len(w) >= 3 and w[-1] not in "aeiou" and w[-2] in "aeiou" and w[-3] not in "aeiou":
                add_var(w + w[-1] + "ed")
                add_var(w + w[-1] + "ing")

    # 3. Yasalma qo'shimchalar (Derivations: -ment, -tion, -able, -ant, -or)
    if w.endswith("ment") and len(w) > 6:
        add_var(w[:-4])
    elif not w.endswith("ment"):
        add_var(w + "ment")

    if w.endswith("tion") and len(w) > 6:
        add_var(w[:-4] + "te")
        add_var(w[:-3])
    if w.endswith("ant") and len(w) > 5:
        add_var(w[:-3])
    elif w.endswith("or") and len(w) > 5:
        add_var(w[:-2])

    # 4. Noto'g'ri fe'llar (Irregular verbs)
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

def _extract_all_words_from_doc(doc) -> Set[str]:
    """
    Kitobdagi barcha mavjud unikal so'zlar to'plamini ajratib oladi (tezkor).
    """
    unique_words = set()
    for page in doc:
        text = page.get_text("text")
        if text:
            words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
            for w in words:
                unique_words.add(w.lower())
    return unique_words

def search_word_in_pdf(
    pdf_path: str,
    query: str,
    max_results: int = 5
) -> Dict[str, Any]:
    """
    Berilgan so'z yoki iborani PDF ichidan mukammal qidiradi.
    1. Aniq moslik.
    2. Morfologik va grammatik variantlar (image -> images, agree -> agreement va h.k.).
    3. AI / Fuzzy yaqin o'xshash so'zlar.
    Natija: Sahifa raqami, kontekst iqtibosi va har bir gapning o'zbekcha mazmuni.
    """
    clean_q = clean_search_query(query)
    if not clean_q:
        return {"total": 0, "results": [], "query": query, "matched_query": query, "definition": None, "note": ""}

    doc = pymupdf.open(pdf_path)

    # 1. Aniq kiritilgan so'z yoki ibora bo'yicha to'g'ridan-to'g'ri qidiruv
    first_attempt = _search_single_term(doc, clean_q, max_results)
    if first_attempt["total"] > 0:
        doc.close()
        definition = get_word_definition(clean_q)
        results = _enrich_results_with_meaning(first_attempt["results"])
        return {
            "total": first_attempt["total"],
            "results": results,
            "query": clean_q,
            "matched_query": clean_q,
            "definition": definition,
            "note": ""
        }

    # 2. Morfologik va grammatik shakllari (birlik, ko'plik, zamon, derivatsiyalar)
    variants = generate_word_variants(clean_q)
    for variant in variants[1:]:
        var_attempt = _search_single_term(doc, variant, max_results)
        if var_attempt["total"] > 0:
            doc.close()
            definition = get_word_definition(clean_q) or get_word_definition(variant)
            results = _enrich_results_with_meaning(var_attempt["results"])
            return {
                "total": var_attempt["total"],
                "results": results,
                "query": clean_q,
                "matched_query": variant,
                "definition": definition,
                "note": f"So'zning kitobdagi shakli: <b>'{variant}'</b>"
            }

    # 3. Ko'p so'zli jumla bo'lsa, qismlarini (sub-phrases) tekshirish
    words = clean_q.split()
    if len(words) >= 3:
        for sub_len in [3, 2]:
            if len(words) >= sub_len:
                sub_phrase = " ".join(words[:sub_len])
                sub_attempt = _search_single_term(doc, sub_phrase, max_results)
                if sub_attempt["total"] > 0:
                    doc.close()
                    definition = get_word_definition(clean_q) or get_word_definition(sub_phrase)
                    results = _enrich_results_with_meaning(sub_attempt["results"])
                    return {
                        "total": sub_attempt["total"],
                        "results": results,
                        "query": clean_q,
                        "matched_query": sub_phrase,
                        "definition": definition,
                        "note": f"Jumlaning kitobdagi asosiy qismi: <b>'{sub_phrase}'</b>"
                    }

    # 4. AI / Fuzzy yaqin o'xshash so'zlar qidiruvi
    all_book_words = _extract_all_words_from_doc(doc)
    q_target = clean_q.lower()
    close_matches = difflib.get_close_matches(q_target, list(all_book_words), n=3, cutoff=0.72)

    if close_matches:
        for matched_word in close_matches:
            fuzzy_attempt = _search_single_term(doc, matched_word, max_results)
            if fuzzy_attempt["total"] > 0:
                doc.close()
                definition = get_word_definition(clean_q)
                results = _enrich_results_with_meaning(fuzzy_attempt["results"])
                return {
                    "total": fuzzy_attempt["total"],
                    "results": results,
                    "query": clean_q,
                    "matched_query": matched_word,
                    "definition": definition,
                    "note": f"Kitobda unga eng yaqin mos keluvchi shakl: <b>'{matched_word}'</b>"
                }

    doc.close()
    return {
        "total": 0,
        "results": [],
        "query": clean_q,
        "matched_query": clean_q,
        "definition": get_word_definition(clean_q),
        "note": ""
    }

def get_total_pages(pdf_path: str) -> int:
    try:
        doc = pymupdf.open(pdf_path)
        pages = len(doc)
        doc.close()
        return pages
    except Exception:
        return 0
