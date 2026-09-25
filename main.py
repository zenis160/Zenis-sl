import asyncio
import json
import logging
import os

from aiohttp import web
from splusthon import SoroushClient, events


# =========================================================
# CONFIG
# =========================================================

PORT = int(os.getenv("PORT", "8000"))

SESSION_FILE = "soroush_session"
DATA_FILE = "data.json"

DEFAULT_REPLY = (
    "سلام، در حال حاضر آفلاین هستم. "
    "بعداً پیام شما را بررسی می‌کنم."
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("SPlusAutoReply")


# =========================================================
# GLOBAL
# =========================================================

bot = None
login_lock = asyncio.Lock()


# =========================================================
# BOT
# =========================================================

class AutoReplyBot:

    def __init__(self):

        self.client = None
        self.me = None

        self.running = True

        self.reply_text = DEFAULT_REPLY

        self.replied_users = set()

        self.logged_in = False

        self.load_data()

    # -----------------------------------------------------
    # DATA
    # -----------------------------------------------------

    def load_data(self):

        if not os.path.exists(DATA_FILE):
            return

        try:

            with open(
                DATA_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            self.reply_text = data.get(
                "reply_text",
                DEFAULT_REPLY
            )

            self.replied_users = set(
                str(x)
                for x in data.get(
                    "replied_users",
                    []
                )
            )

            self.running = data.get(
                "running",
                True
            )

        except Exception as e:

            logger.error(
                "Data loading error: %s",
                e
            )

    def save_data(self):

        try:

            with open(
                DATA_FILE,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    {
                        "reply_text": self.reply_text,
                        "replied_users": list(
                            self.replied_users
                        ),
                        "running": self.running
                    },
                    f,
                    ensure_ascii=False,
                    indent=2
                )

        except Exception as e:

            logger.error(
                "Data saving error: %s",
                e
            )

    # -----------------------------------------------------
    # SEND MESSAGE
    # -----------------------------------------------------

    async def send_message(
        self,
        event,
        text
    ):

        try:

            await self.client.send_message(
                event.chat_id,
                text
            )

        except Exception as e:

            logger.error(
                "Send message error: %s",
                e
            )

    # -----------------------------------------------------
    # LOGIN
    # -----------------------------------------------------

    async def login(
        self,
        phone,
        code
    ):

        if self.logged_in:
            return True

        async with login_lock:

            if self.logged_in:
                return True

            logger.info(
                "Connecting to SPlus..."
            )

            self.client = SoroushClient(
                SESSION_FILE
            )

            async def code_callback():

                return code

            await self.client.start(
                phone=phone,
                code_callback=code_callback
            )

            self.me = await self.client.get_me()

            self.logged_in = True

            logger.info(
                "Login successful: %s",
                getattr(
                    self.me,
                    "first_name",
                    "Unknown"
                )
            )

            # ---------------------------------------------
            # MESSAGE HANDLER
            # ---------------------------------------------

            @self.client.on(events.NewMessage)
            async def handler(event):

                try:

                    text = (
                        event.raw_text or ""
                    ).strip()

                    if not text:
                        return

                    # =====================================
                    # COMMANDS FROM OWNER
                    # =====================================

                    if event.out:

                        # راهنما
                        if text in (
                            "راهنما",
                            "help"
                        ):

                            await self.send_message(
                                event,
                                "🤖 راهنمای ربات\n\n"
                                "فعال\n"
                                "خاموش\n"
                                "وضعیت\n"
                                "پاک\n\n"
                                "تغییر متن:\n"
                                "متن متن موردنظر\n\n"
                                "مثال:\n"
                                "متن سلام، الان آفلاین هستم."
                            )

                            return

                        # تغییر متن
                        if text.startswith("متن "):

                            new_text = text[5:].strip()

                            if not new_text:

                                await self.send_message(
                                    event,
                                    "❌ متن خالی است."
                                )

                                return

                            self.reply_text = new_text

                            self.save_data()

                            await self.send_message(
                                event,
                                "✅ متن پاسخ تغییر کرد."
                            )

                            return

                        # فعال
                        if text == "فعال":

                            self.running = True

                            self.save_data()

                            await self.send_message(
                                event,
                                "✅ پاسخ خودکار فعال شد."
                            )

                            return

                        # خاموش
                        if text == "خاموش":

                            self.running = False

                            self.save_data()

                            await self.send_message(
                                event,
                                "⛔ پاسخ خودکار خاموش شد."
                            )

                            return

                        # پاک
                        if text == "پاک":

                            self.replied_users.clear()

                            self.save_data()

                            await self.send_message(
                                event,
                                "✅ لیست افراد پاک شد."
                            )

                            return

                        # وضعیت
                        if text == "وضعیت":

                            status = (
                                "فعال"
                                if self.running
                                else "خاموش"
                            )

                            await self.send_message(
                                event,
                                "📊 وضعیت\n\n"
                                f"ربات: {status}\n"
                                f"تعداد پاسخ‌ها: "
                                f"{len(self.replied_users)}\n\n"
                                f"متن فعلی:\n"
                                f"{self.reply_text}"
                            )

                            return

                        return

                    # =====================================
                    # INCOMING PRIVATE MESSAGE
                    # =====================================

                    if not self.running:
                        return

                    # فقط PV
                    if hasattr(
                        event,
                        "is_private"
                    ):

                        if not event.is_private:
                            return

                    # شناسه فرستنده
                    sender_id = getattr(
                        event,
                        "sender_id",
                        None
                    )

                    if sender_id is None:

                        sender_id = getattr(
                            event,
                            "chat_id",
                            None
                        )

                    if sender_id is None:
                        return

                    sender_id = str(
                        sender_id
                    )

                    # قبلاً پاسخ داده؟
                    if sender_id in self.replied_users:
                        return

                    # ثبت قبل از ارسال
                    self.replied_users.add(
                        sender_id
                    )

                    self.save_data()

                    # پاسخ
                    await self.send_message(
                        event,
                        self.reply_text
                    )

                    logger.info(
                        "Auto reply sent to %s",
                        sender_id
                    )

                except Exception as e:

                    logger.exception(
                        "Message handler error: %s",
                        e
                    )

            logger.info(
                "Auto reply handler started."
            )

            return True

    # -----------------------------------------------------
    # RUN CLIENT
    # -----------------------------------------------------

    async def run_client(self):

        if not self.client:
            return

        try:

            await self.client.run_until_disconnected()

        except Exception as e:

            logger.exception(
                "Client disconnected: %s",
                e
            )

            self.logged_in = False


# =========================================================
# WEB PAGE
# =========================================================

HTML = """
<!DOCTYPE html>

<html lang="fa" dir="rtl">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>SPlus Auto Reply</title>

<style>

body {
    font-family: Arial, sans-serif;
    background: #111827;
    color: white;
    margin: 0;
    padding: 30px;
}

.container {
    max-width: 500px;
    margin: auto;
}

.card {
    background: #1f2937;
    padding: 25px;
    border-radius: 15px;
}

input {
    width: 100%;
    box-sizing: border-box;
    padding: 13px;
    margin: 8px 0;
    border-radius: 8px;
    border: none;
}

button {
    width: 100%;
    padding: 13px;
    margin-top: 10px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
}

.status {
    margin-top: 20px;
    padding: 12px;
    background: #374151;
    border-radius: 8px;
}

</style>

</head>

<body>

<div class="container">

<div class="card">

<h2>SPlus Auto Reply</h2>

<form method="POST"
      action="/login">

<input
    name="phone"
    placeholder="شماره سروش"
    required
>

<input
    name="code"
    placeholder="کد تأیید"
    required
>

<button type="submit">
ورود
</button>

</form>

<div class="status">

وضعیت:
{{STATUS}}

</div>

</div>

</div>

</body>

</html>
"""


# =========================================================
# WEB ROUTES
# =========================================================

async def index(request):

    status = (
        "متصل"
        if bot and bot.logged_in
        else "وارد نشده"
    )

    html = HTML.replace(
        "{{STATUS}}",
        status
    )

    return web.Response(
        text=html,
        content_type="text/html"
    )


async def login(request):

    try:

        data = await request.post()

        phone = data.get(
            "phone",
            ""
        ).strip()

        code = data.get(
            "code",
            ""
        ).strip()

        if not phone or not code:

            return web.Response(
                text="شماره و کد الزامی است.",
                status=400
            )

        await bot.login(
            phone,
            code
        )

        asyncio.create_task(
            bot.run_client()
        )

        return web.Response(
            text=(
                "ورود موفق بود. "
                "ربات فعال شد."
            ),
            content_type="text/plain"
        )

    except Exception as e:

        logger.exception(
            "Login error"
        )

        return web.Response(
            text=f"Login failed: {e}",
            status=500
        )


async def health(request):

    return web.json_response(
        {
            "status": "ok",
            "logged_in": (
                bot.logged_in
                if bot
                else False
            )
        }
    )


# =========================================================
# WEB SERVER
# =========================================================

async def start_web():

    app = web.Application()

    app.router.add_get(
        "/",
        index
    )

    app.router.add_post(
        "/login",
        login
    )

    app.router.add_get(
        "/health",
        health
    )

    runner = web.AppRunner(
        app
    )

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

    logger.info(
        "Web server started on port %s",
        PORT
    )

    return runner


# =========================================================
# MAIN
# =========================================================

async def main():

    global bot

    bot = AutoReplyBot()

    await start_web()

    logger.info(
        "SPlus Auto Reply is ready."
    )

    # جلوگیری از بسته شدن برنامه
    while True:

        await asyncio.sleep(3600)


if __name__ == "__main__":

    try:
        asyncio.run(main())

    except KeyboardInterrupt:

        logger.info(
            "Application stopped."
        )