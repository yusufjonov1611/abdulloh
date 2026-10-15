import pymupdf
import io
import re
from typing import List, Dict, Any, Optional
from vocabulary import get_word_definition

def generate_word_variants(query: str) -> List[str]:
    """
    So'zning boshqa zamon, ko'plik/birlik (inflectional/morphological)
    va asosiy shakllarini hosil qiladi.
    """
    w = query.strip().lower()
    variants = []
    
    def add_var(v: str):
        v = v.strip().lower()
        if len(v) >= 3 and v not in variants and v != w:
            variants.append(v)

    if " " in w or len(w) < 3:
        return [query.strip()]

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

    return [query.strip()] + variants

def _search_single_term(doc, term: str, max_results: int = 8) -> Dict[str, Any]:
    """
    Qidirilgan so'zning sahifa, qator raqami va gapini aniqlaydi.
    """
    total_occurrences = 0
    results: List[Dict[str, Any]] = []
    seen_texts = set()

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_num = page_index + 1

        raw_lines = page.get_text("text").splitlines()
        numbered_lines = []
        for i, l in enumerate(raw_lines, 1):
            if l.strip():
                numbered_lines.append((i, l.strip()))

        blocks = page.get_text("blocks")

        for line_num, line_str in numbered_lines:
            if term.lower() in line_str.lower():
                total_occurrences += 1

                # Qatordagi to'liq gap yoki blokni topish
                matched_block_text = line_str
                for b in blocks:
                    b_raw = b[4].strip()
                    if line_str in b_raw:
                        matched_block_text = " ".join(b_raw.split())
                        break

                # Agar faqat ro'yxat bo'lsa (masalan, 'l judge'), uzunroq va mazmunli blokni afzal ko'ramiz
                if len(matched_block_text.split()) < 6 or matched_block_text.startswith("l "):
                    for b in blocks:
                        b_cand = " ".join(b[4].split())
                        if term.lower() in b_cand.lower() and len(b_cand.split()) > len(matched_block_text.split()) and not b_cand.startswith("l "):
                            matched_block_text = b_cand
                            break

                key = (page_num, matched_block_text)
                if key not in seen_texts:
                    seen_texts.add(key)
                    if len(results) < max_results:
                        results.append({
                            "page": page_num,
                            "line": line_num,
                            "line_exact": line_str,
                            "sentence": matched_block_text
                        })

    return {
        "total": total_occurrences,
        "results": results
    }

def search_word_in_pdf(
    pdf_path: str,
    query: str,
    max_results: int = 8
) -> Dict[str, Any]:
    """
    Berilgan so'zni qidiradi.
    Sahifa raqami, qator raqami, o'sha qatordagi to'liq gap va so'z ma'nosini qaytaradi.
    """
    clean_query = query.strip()
    if not clean_query:
        return {"total": 0, "results": [], "query": query, "matched_query": query, "definition": None}

    doc = pymupdf.open(pdf_path)

    # 1. To'g'ridan-to'g'ri qidiruv
    first_attempt = _search_single_term(doc, clean_query, max_results)
    if first_attempt["total"] > 0:
        doc.close()
        definition = get_word_definition(clean_query)
        return {
            "total": first_attempt["total"],
            "results": first_attempt["results"],
            "query": clean_query,
            "matched_query": clean_query,
            "definition": definition
        }

    # 2. Zamon va shakllari bo'yicha qidiruv
    doc.close()
    variants = generate_word_variants(clean_query)
    
    for variant in variants[1:]:
        doc_var = pymupdf.open(pdf_path)
        var_attempt = _search_single_term(doc_var, variant, max_results)
        doc_var.close()

        if var_attempt["total"] > 0:
            definition = get_word_definition(variant) or get_word_definition(clean_query)
            return {
                "total": var_attempt["total"],
                "results": var_attempt["results"],
                "query": clean_query,
                "matched_query": variant,
                "definition": definition
            }

    return {
        "total": 0,
        "results": [],
        "query": clean_query,
        "matched_query": clean_query,
        "definition": get_word_definition(clean_query)
    }

def get_total_pages(pdf_path: str) -> int:
    try:
        doc = pymupdf.open(pdf_path)
        pages = len(doc)
        doc.close()
        return pages
    except Exception:
        return 0
