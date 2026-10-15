import os
import aiohttp
from aiohttp import web
import asyncio

async def handle_health(request):
    return web.json_response({"status": "ok", "service": "KitobBot"})

async def handle_book(request):
    book_path = os.getenv("BOOK_PATH", "books/book.pdf")
    if os.path.exists(book_path):
        return web.FileResponse(
            path=book_path,
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'inline; filename="book.pdf"'
            }
        )
    return web.Response(text="Kitob fayli topilmadi.", status=404)

def setup_web_app():
    app = web.Application()
    app.router.add_get('/', handle_health)
    app.router.add_get('/health', handle_health)
    app.router.add_get('/book', handle_book)
    return app
