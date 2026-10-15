import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any

DATA_FILE = "data.json"

# 1-Super Admin ID (kod ichida doimiy saqlanadi)
SUPER_ADMIN_ID = 6169032422
SUPER_ADMIN_IDS = [6169032422, 8869543627]

DEFAULT_BOOKS = {
    "1": {
        "id": "1",
        "name": "The Lawyer's English Language Coursebook",
        "path": "books/book.pdf",
        "pages": 412,
        "is_active": True,
        "url": "https://files.catbox.moe/9vv502.pdf"
    }
}

DEFAULT_DATA = {
    "second_admin_id": None,
    "channels": [],
    "users": {},
    "books": DEFAULT_BOOKS
}

def load_data() -> Dict[str, Any]:
    if not os.path.exists(DATA_FILE):
        save_data(DEFAULT_DATA)
        return DEFAULT_DATA.copy()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "books" not in data or not data["books"]:
                data["books"] = DEFAULT_BOOKS.copy()
                save_data(data)
            return data
    except Exception:
        return DEFAULT_DATA.copy()

def save_data(data: Dict[str, Any]):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_super_admin(user_id: int) -> bool:
    return int(user_id) in SUPER_ADMIN_IDS

def is_admin(user_id: int) -> bool:
    if is_super_admin(user_id):
        return True
    data = load_data()
    sec_id = data.get("second_admin_id")
    if sec_id and int(user_id) == int(sec_id):
        return True
    return False

def get_second_admin() -> Optional[int]:
    data = load_data()
    return data.get("second_admin_id")

def set_second_admin(admin_id: int):
    data = load_data()
    data["second_admin_id"] = int(admin_id)
    save_data(data)

def remove_second_admin():
    data = load_data()
    data["second_admin_id"] = None
    save_data(data)

def get_channels() -> List[str]:
    data = load_data()
    return data.get("channels", [])

def add_channel(channel: str) -> bool:
    data = load_data()
    ch = channel.strip()
    if ch not in data["channels"]:
        data["channels"].append(ch)
        save_data(data)
        return True
    return False

def remove_channel(channel: str) -> bool:
    data = load_data()
    ch = channel.strip()
    if ch in data["channels"]:
        data["channels"].remove(ch)
        save_data(data)
        return True
    return False

def register_user(user_id: int, first_name: str, username: Optional[str]):
    data = load_data()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "first_name": first_name or "",
            "username": username or "",
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_data(data)

def get_users_count() -> int:
    data = load_data()
    return len(data.get("users", {}))

def get_users_list(limit: int = 50) -> List[Dict[str, Any]]:
    data = load_data()
    users = data.get("users", {})
    res = []
    for uid, info in list(users.items())[-limit:]:
        res.append({
            "id": uid,
            "name": info.get("first_name", ""),
            "username": info.get("username", ""),
            "joined_at": info.get("joined_at", "")
        })
    return res

# --- Kitoblar boshqaruvi funksiyalari ---
def get_all_books() -> List[Dict[str, Any]]:
    data = load_data()
    books = data.get("books", {})
    return list(books.values())

def get_active_book() -> Optional[Dict[str, Any]]:
    data = load_data()
    books = data.get("books", {})
    for b in books.values():
        if b.get("is_active"):
            return b
    if books:
        # Agar hech qaysi faol bo'lmasa birinchisini faol qilish
        first_key = list(books.keys())[0]
        books[first_key]["is_active"] = True
        save_data(data)
        return books[first_key]
    return None

def set_active_book(book_id: str) -> bool:
    data = load_data()
    books = data.get("books", {})
    if str(book_id) in books:
        for bid in books:
            books[bid]["is_active"] = (bid == str(book_id))
        save_data(data)
        return True
    return False

def add_new_book(name: str, path: str, pages: int, url: str = None) -> str:
    data = load_data()
    books = data.get("books", {})
    new_id = str(len(books) + 1)
    while new_id in books:
        new_id = str(int(new_id) + 1)

    # Yangi kitobni faol qilish
    for bid in books:
        books[bid]["is_active"] = False

    books[new_id] = {
        "id": new_id,
        "name": name.strip(),
        "path": path,
        "pages": pages,
        "is_active": True,
        "url": url,
        "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    data["books"] = books
    save_data(data)
    return new_id

def delete_book(book_id: str) -> bool:
    data = load_data()
    books = data.get("books", {})
    bid = str(book_id)
    if bid in books:
        was_active = books[bid].get("is_active", False)
        # Faylni ham o'chirish (agar mavjud bo'lsa)
        path = books[bid].get("path")
        if path and os.path.exists(path) and path != "books/book.pdf":
            try:
                os.remove(path)
            except Exception:
                pass
        del books[bid]
        if was_active and books:
            first_key = list(books.keys())[0]
            books[first_key]["is_active"] = True
        data["books"] = books
        save_data(data)
        return True
    return False
