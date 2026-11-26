"""Self-registration safeguards: an image challenge ("I am not a robot") and an e-mailed code.

The captcha is stateless: the answer travels only as a salted hash inside a signed, expiring token,
so it works with any number of server processes. The picture is a PNG drawn on the server, the
characters never appear as text in the page.
"""
import base64
import hashlib
import hmac
import io
import random
import secrets

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.mail import EmailMultiAlternatives
from PIL import Image, ImageDraw, ImageFilter, ImageFont

CAPTCHA_ALPHABET = "ABCDEFHJKMNPRSTUVWXY2345678"  # no look-alikes (0/O, 1/I/L, 9/g)
CAPTCHA_SALT = "dz.captcha"
CAPTCHA_MAX_AGE = 600  # seconds


def _answer_hash(answer):
    return hmac.new(settings.SECRET_KEY.encode(), answer.strip().upper().encode(), hashlib.sha256).hexdigest()


def _draw(text):
    w, h = 240, 80
    img = Image.new("RGB", (w, h), (238, 244, 252))
    d = ImageDraw.Draw(img)
    rnd = random.SystemRandom()
    for _ in range(6):  # background noise lines
        d.line([(rnd.randint(0, w), rnd.randint(0, h)), (rnd.randint(0, w), rnd.randint(0, h))],
               fill=(rnd.randint(140, 200), rnd.randint(160, 210), rnd.randint(200, 240)), width=2)
    try:
        font = ImageFont.load_default(size=44)
    except TypeError:  # very old Pillow
        font = ImageFont.load_default()
    x = 18
    for ch in text:
        tile = Image.new("RGBA", (60, 70), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((10, 6), ch, font=font,
                                  fill=(rnd.randint(10, 60), rnd.randint(40, 90), rnd.randint(120, 190), 255))
        tile = tile.rotate(rnd.uniform(-28, 28), resample=Image.BICUBIC, expand=False)
        img.paste(tile, (x, rnd.randint(-2, 12)), tile)
        x += rnd.randint(36, 42)
    for _ in range(3):  # lines across the characters
        y1, y2 = rnd.randint(15, h - 15), rnd.randint(15, h - 15)
        d.line([(0, y1), (w, y2)], fill=(rnd.randint(30, 90), rnd.randint(60, 120), rnd.randint(150, 210)), width=2)
    for _ in range(220):
        d.point((rnd.randint(0, w - 1), rnd.randint(0, h - 1)), fill=(rnd.randint(60, 160),) * 3)
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def make_captcha(length=5):
    """-> (token, image data URL, answer). The answer is for tests only; the view never returns it."""
    answer = "".join(secrets.choice(CAPTCHA_ALPHABET) for _ in range(length))
    token = signing.dumps({"h": _answer_hash(answer), "n": secrets.token_hex(8)}, salt=CAPTCHA_SALT)
    return token, _draw(answer), answer


def check_captcha(token, answer):
    """True once per token: a solved picture cannot be replayed."""
    try:
        data = signing.loads(token or "", salt=CAPTCHA_SALT, max_age=CAPTCHA_MAX_AGE)
    except signing.BadSignature:
        return False
    if not hmac.compare_digest(data.get("h", ""), _answer_hash(answer or "")):
        return False
    key = "captcha-used:" + hashlib.sha256(token.encode()).hexdigest()
    return cache.add(key, 1, CAPTCHA_MAX_AGE)  # False when it was already used


# --------------------------------------------------------------------------- e-mail code
CODE_TTL_MINUTES = 10
CODE_MAX_ATTEMPTS = 5
RESEND_AFTER_SECONDS = 60


def new_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def mask_email(email):
    name, _, domain = email.partition("@")
    shown = name[:2] if len(name) > 2 else name[:1]
    return f"{shown}{'*' * max(1, len(name) - len(shown))}@{domain}"


def send_code(email, first_name, code):
    subject = f"Dreamzone: tasdiqlash kodi {code}"
    text = (f"Salom, {first_name}!\n\nDreamzone'da ro'yxatdan o'tish uchun tasdiqlash kodingiz: {code}\n"
            f"Kod {CODE_TTL_MINUTES} daqiqa amal qiladi. Agar siz ro'yxatdan o'tmagan bo'lsangiz, bu xatni e'tiborsiz qoldiring.\n\n"
            f"Your Dreamzone verification code: {code} (valid for {CODE_TTL_MINUTES} minutes).")
    html = (f'<div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:24px;color:#0b1b38">'
            f'<h2 style="color:#0a8cf5;margin:0 0 12px">Dreamzone</h2><p>Salom, {first_name}!</p>'
            f'<p>Ro\'yxatdan o\'tish uchun tasdiqlash kodingiz:</p>'
            f'<p style="font-size:34px;font-weight:700;letter-spacing:8px;background:#eff8ff;border-radius:12px;'
            f'padding:14px 0;text-align:center;margin:16px 0">{code}</p>'
            f'<p style="color:#47546b;font-size:13px">Kod {CODE_TTL_MINUTES} daqiqa amal qiladi. Agar siz ro\'yxatdan '
            f'o\'tmagan bo\'lsangiz, bu xatni e\'tiborsiz qoldiring.</p></div>')
    msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [email])
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)
