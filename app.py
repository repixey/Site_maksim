import os
import random
import string
import uuid
from datetime import datetime, timezone
from functools import wraps

from captcha.image import ImageCaptcha
from flask import (
    Flask, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import (
    LoginManager, UserMixin, current_user, login_required, login_user, logout_user
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import get_db, seed_db

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, "static", "uploads")
AVATAR_DIR = os.path.join(UPLOAD_ROOT, "avatars")
SERVICE_IMG_DIR = os.path.join(UPLOAD_ROOT, "services")
SPEC_IMG_DIR = os.path.join(UPLOAD_ROOT, "specialists")
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "garage-super-secret-key-2026")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per minute", "20 per second"],
    storage_uri="memory://"
)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Войдите, чтобы продолжить."
login_manager.login_message_category = "info"


def query_db(query, args=(), one=False):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    rv = cur.fetchall()
    conn.close()
    return (rv[0] if rv else None) if one else rv


def execute_db(query, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    conn.close()
    return cur.lastrowid


def _ensure_dirs():
    os.makedirs(AVATAR_DIR, exist_ok=True)
    os.makedirs(SERVICE_IMG_DIR, exist_ok=True)
    os.makedirs(SPEC_IMG_DIR, exist_ok=True)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def save_upload(file_storage, folder):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = secure_filename(file_storage.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    abs_dir = os.path.join(UPLOAD_ROOT, folder)
    os.makedirs(abs_dir, exist_ok=True)
    file_storage.save(os.path.join(abs_dir, filename))
    return f"uploads/{folder}/{filename}"


def verify_captcha():
    expected = session.get("captcha_code")
    user_val = request.form.get("captcha", "").strip()
    if not expected or not user_val or expected.upper() != user_val.upper():
        return False
    session.pop("captcha_code", None)
    return True


def get_session_id():
    if "chat_session_id" not in session:
        session["chat_session_id"] = uuid.uuid4().hex
    return session["chat_session_id"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def add_notification(user_id, message, ntype="info"):
    execute_db(
        "INSERT INTO notifications (id, user_id, message, ntype, is_read, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (uuid.uuid4().hex, user_id, message, ntype, now_iso())
    )


class User(UserMixin):
    def __init__(self, row):
        self.id = row["id"]
        self.username = row["username"]
        self.email = row["email"]
        self.password_hash = row["password_hash"]
        self.phone = row["phone"]
        self.is_admin = bool(row["is_admin"])
        self.avatar = row["avatar"]
        self.bonus_points = row["bonus_points"]
        self.created_at = row["created_at"]

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    row = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    return User(row) if row else None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


CATEGORIES = [
    {"slug": "all", "title": "Все услуги"},
    {"slug": "dealers", "title": "Автосалоны"},
    {"slug": "service", "title": "ТО и ремонт"},
    {"slug": "tires", "title": "Шиномонтаж"},
    {"slug": "insurance", "title": "Страхование"},
    {"slug": "testdrive", "title": "Тест-драйв"},
    {"slug": "tuning", "title": "Тюнинг"},
    {"slug": "detailing", "title": "Детейлинг"},
    {"slug": "finance", "title": "Кредит и лизинг"},
]
CATEGORY_LOOKUP = {c["slug"]: c["title"] for c in CATEGORIES}

CHAT_ROOMS = {"support", "colleagues", "general"}


@app.context_processor
def inject_globals():
    return {
        'now': datetime.now(timezone.utc)
    }


@app.route("/captcha.png")
def captcha_img():
    code = "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
    session["captcha_code"] = code
    image = ImageCaptcha(width=150, height=48)
    data = image.generate(code)
    return Response(data.getvalue(), mimetype="image/png")


@app.route("/")
def index():
    services = [dict(s) for s in query_db("SELECT * FROM services ORDER BY created_at DESC LIMIT 8")]
    stations = [dict(s) for s in query_db("SELECT * FROM stations ORDER BY name")]

    stats = {
        "stations": query_db("SELECT COUNT(*) c FROM stations", one=True)["c"],
        "specialists": query_db("SELECT COUNT(*) c FROM specialists", one=True)["c"],
        "clients": query_db("SELECT COUNT(*) c FROM users", one=True)["c"],
        "avg_rating": query_db("SELECT AVG(stars) a FROM reviews", one=True)["a"] or 5.0,
    }

    next_appt = None
    notifications = []
    if current_user.is_authenticated:
        row = query_db("""
            SELECT a.*, s.title as service_title, sp.name as specialist_name, st.name as station_name
            FROM appointments a
            LEFT JOIN services s ON a.service_id = s.id
            LEFT JOIN specialists sp ON a.specialist_id = sp.id
            LEFT JOIN stations st ON a.station_id = st.id
            WHERE a.user_id = ? AND a.status != 'Отменена'
            ORDER BY a.date ASC, a.time ASC LIMIT 1
        """, (current_user.id,), one=True)
        next_appt = dict(row) if row else None
        notifications = [dict(n) for n in query_db(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 5",
            (current_user.id,)
        )]

    return render_template(
        "index.html",
        categories=CATEGORIES,
        services=services,
        stations=stations,
        stats=stats,
        next_appt=next_appt,
        notifications=notifications,
    )


@app.route("/announcements")
def announcements():
    # Попытка получить объявления из БД; если таблицы/запроса нет — вернём пустой список,
    # чтобы не ломать отображение сайта.
    try:
        rows = query_db("SELECT * FROM announcements ORDER BY created_at DESC")
        announcements = [dict(r) for r in rows] if rows else []
    except Exception:
        announcements = []
    return render_template("announcements.html", announcements=announcements, categories=CATEGORIES)


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        error = None
        if not verify_captcha():
            error = "Неверно введен код с картинки (капча)."
        elif not username or not email or not password:
            error = "Заполните все обязательные поля."
        elif password != password2:
            error = "Пароли не совпадают."
        elif len(password) < 6:
            error = "Пароль должен быть не короче 6 символов."
        elif query_db("SELECT id FROM users WHERE LOWER(username) = ?", (username.lower(),), one=True):
            error = "Такой логин уже занят."
        elif query_db("SELECT id FROM users WHERE LOWER(email) = ?", (email.lower(),), one=True):
            error = "Этот email уже зарегистрирован."

        if error:
            flash(error, "error")
            return render_template("register.html", form=request.form)

        user_id = uuid.uuid4().hex
        pwd_hash = generate_password_hash(password)

        execute_db("""
            INSERT INTO users (id, username, email, password_hash, phone, is_admin, avatar, bonus_points, created_at)
            VALUES (?, ?, ?, ?, ?, 0, NULL, 0, ?)
        """, (user_id, username, email, pwd_hash, phone, now_iso()))

        row = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
        login_user(User(row))
        add_notification(user_id, "Добро пожаловать в AUTO•PRO! Ваш аккаунт создан.", "success")
        flash("Регистрация успешна. Добро пожаловать!", "success")
        return redirect(url_for("profile_view", user_id=user_id))

    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        login_id = request.form.get("login", "").strip().lower()
        password = request.form.get("password", "")
        remember = bool(request.form.get("remember"))

        if not verify_captcha():
            flash("Неверно введен код с картинки (капча).", "error")
            return render_template("login.html")

        row = query_db(
            "SELECT * FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?",
            (login_id, login_id),
            one=True
        )

        if row and check_password_hash(row["password_hash"], password):
            user = User(row)
            login_user(user, remember=remember)
            flash(f"С возвращением, {user.username}!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("index"))

        flash("Неверный логин или пароль.", "error")

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из аккаунта.", "info")
    return redirect(url_for("index"))


@app.route("/services")
def services_list():
    category = request.args.get("category", "all")
    if category and category != "all":
        rows = query_db("SELECT * FROM services WHERE category = ? ORDER BY created_at DESC", (category,))
    else:
        rows = query_db("SELECT * FROM services ORDER BY created_at DESC")
    services = [dict(s) for s in rows]
    return render_template("services.html", categories=CATEGORIES, services=services, active_category=category)


@app.route("/service/<service_id>")
def service_detail(service_id):
    s_row = query_db("SELECT * FROM services WHERE id = ?", (service_id,), one=True)
    if not s_row:
        abort(404)
    service = dict(s_row)
    specialists = [dict(sp) for sp in query_db("SELECT * FROM specialists ORDER BY rating DESC")]
    stations = [dict(s) for s in query_db("SELECT * FROM stations ORDER BY name")]
    return render_template(
        "service_detail.html",
        service=service,
        specialists=specialists,
        stations=stations,
        category_title=CATEGORY_LOOKUP.get(service.get("category"), service.get("category")),
    )


@app.route("/stations")
def stations_list():
    station_id = request.args.get("station_id", "")
    stations = [dict(s) for s in query_db("SELECT * FROM stations ORDER BY name")]
    if station_id:
        specialists = [dict(sp) for sp in query_db(
            "SELECT * FROM specialists WHERE station_id = ? ORDER BY rating DESC", (station_id,)
        )]
    else:
        specialists = [dict(sp) for sp in query_db("SELECT * FROM specialists ORDER BY rating DESC")]
    return render_template(
        "stations.html", stations=stations, specialists=specialists, active_station=station_id
    )


@app.route("/booking", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def booking():
    stations = [dict(s) for s in query_db("SELECT * FROM stations ORDER BY name")]
    services = [dict(s) for s in query_db("SELECT * FROM services ORDER BY title")]
    specialists = [dict(sp) for sp in query_db("SELECT * FROM specialists ORDER BY name")]

    if request.method == "POST":
        if not verify_captcha():
            flash("Неверный код с картинки (капча). Попробуйте еще раз.", "error")
            return redirect(url_for("booking"))

        station_id = request.form.get("station_id", "").strip() or None
        service_id = request.form.get("service_id", "").strip() or None
        specialist_id = request.form.get("specialist_id", "").strip() or None
        user_name = request.form.get("user_name", "").strip()
        user_phone = request.form.get("user_phone", "").strip()
        date_val = request.form.get("date", "").strip()
        time_val = request.form.get("time", "").strip()
        car_info = request.form.get("car_info", "").strip()
        comment = request.form.get("comment", "").strip()

        if not user_name or not user_phone or not date_val or not time_val:
            flash("Пожалуйста, заполните имя, телефон, дату и время записи.", "error")
            return redirect(url_for("booking"))

        appt_id = uuid.uuid4().hex
        user_id = current_user.id if current_user.is_authenticated else None

        execute_db("""
            INSERT INTO appointments
            (id, user_id, station_id, user_name, user_phone, service_id, specialist_id, date, time, car_info, comment, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Ожидает', ?)
        """, (appt_id, user_id, station_id, user_name, user_phone, service_id, specialist_id,
              date_val, time_val, car_info, comment, now_iso()))

        if user_id:
            add_notification(user_id, f"Заявка на запись {date_val} в {time_val} принята в обработку.", "warn")

        flash("Заявка на запись успешно оформлена! Менеджер свяжется с вами для подтверждения.", "success")
        if current_user.is_authenticated:
            return redirect(url_for("profile_view", user_id=current_user.id))
        return redirect(url_for("index"))

    preselected_service = request.args.get("service_id", "")
    return render_template(
        "booking.html", stations=stations, services=services, specialists=specialists,
        preselected_service=preselected_service
    )


@app.route("/appointments")
@login_required
def my_appointments():
    rows = query_db("""
        SELECT a.*, s.title as service_title, sp.name as specialist_name, st.name as station_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN specialists sp ON a.specialist_id = sp.id
        LEFT JOIN stations st ON a.station_id = st.id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
    """, (current_user.id,))
    appointments = [dict(a) for a in rows]
    return render_template("appointments.html", appointments=appointments)


@app.route("/appointments/<appt_id>/cancel", methods=["POST"])
@login_required
def cancel_appointment(appt_id):
    row = query_db("SELECT * FROM appointments WHERE id = ?", (appt_id,), one=True)
    if not row or (row["user_id"] != current_user.id and not current_user.is_admin):
        abort(403)
    execute_db("UPDATE appointments SET status = 'Отменена' WHERE id = ?", (appt_id,))
    flash("Запись отменена.", "info")
    return redirect(url_for("my_appointments"))


@app.route("/reviews", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def reviews():
    if request.method == "POST":
        if not current_user.is_authenticated and not verify_captcha():
            flash("Неверный код с картинки (капча).", "error")
            return redirect(url_for("reviews"))

        stars = max(1, min(5, int(request.form.get("stars", 5) or 5)))
        text = request.form.get("text", "").strip()
        author_name = current_user.username if current_user.is_authenticated else (
            request.form.get("author_name", "").strip() or "Гость"
        )
        if not text:
            flash("Добавьте текст отзыва.", "error")
            return redirect(url_for("reviews"))

        execute_db("""
            INSERT INTO reviews (id, user_id, author_name, service_id, stars, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            uuid.uuid4().hex,
            current_user.id if current_user.is_authenticated else None,
            author_name, request.form.get("service_id") or None, stars, text, now_iso()
        ))
        flash("Спасибо! Отзыв опубликован.", "success")
        return redirect(url_for("reviews"))

    rows = [dict(r) for r in query_db("SELECT * FROM reviews ORDER BY created_at DESC LIMIT 50")]
    agg = query_db("SELECT AVG(stars) avg_stars, COUNT(*) total FROM reviews", one=True)
    five_star = query_db("SELECT COUNT(*) c FROM reviews WHERE stars = 5", one=True)["c"]
    total = agg["total"] or 0
    five_star_pct = round((five_star / total) * 100) if total else 0
    services = [dict(s) for s in query_db("SELECT id, title FROM services ORDER BY title")]
    return render_template(
        "reviews.html", reviews=rows, avg_stars=agg["avg_stars"] or 5.0,
        total=total, five_star_pct=five_star_pct, services=services
    )


@app.route("/promos")
def promos():
    rows = query_db("""
        SELECT * FROM services WHERE old_price IS NOT NULL AND old_price > price
        ORDER BY created_at DESC
    """)
    promo_services = [dict(s) for s in rows]
    return render_template("promos.html", services=promo_services)


@app.route("/notifications")
@login_required
def notifications_view():
    rows = query_db(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC", (current_user.id,)
    )
    return render_template("notifications.html", notifications=[dict(n) for n in rows])


@app.route("/notifications/read-all", methods=["POST"])
@login_required
def notifications_read_all():
    execute_db("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (current_user.id,))
    return redirect(url_for("notifications_view"))


@app.route("/chats")
def chats_view():
    return render_template("chats.html", is_staff=current_user.is_authenticated and current_user.is_admin)


def _room_filter(room):
    if room == "support":
        sid = get_session_id()
        if current_user.is_authenticated:
            return "(user_id = ? OR session_id = ?) AND room = 'support'", (current_user.id, sid)
        return "session_id = ? AND room = 'support'", (sid,)
    return "room = ?", (room,)


@app.route("/api/chat/<room>/messages")
def chat_messages(room):
    if room not in CHAT_ROOMS:
        abort(404)
    if room in ("colleagues", "general") and not current_user.is_authenticated:
        abort(403)
    where, args = _room_filter(room)
    rows = query_db(f"SELECT * FROM chat_messages WHERE {where} ORDER BY created_at ASC", args)
    return jsonify([dict(r) for r in rows])


@app.route("/api/chat/<room>/send", methods=["POST"])
@limiter.limit("30 per minute")
def chat_send(room):
    if room not in CHAT_ROOMS:
        abort(404)
    if room in ("colleagues", "general") and not current_user.is_authenticated:
        abort(403)

    data = request.get_json(silent=True) or request.form
    text = data.get("message", "").strip()
    if not text:
        return jsonify({"status": "error", "message": "Пустое сообщение"}), 400

    sid = get_session_id()
    user_id = current_user.id if current_user.is_authenticated else None
    sender_name = current_user.username if current_user.is_authenticated else "Гость"

    session_id_val = sid if room == "support" else None
    execute_db("""
        INSERT INTO chat_messages (id, room, user_id, session_id, sender_name, message, is_admin, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
    """, (uuid.uuid4().hex, room, user_id, session_id_val, sender_name, text, now_iso()))

    if room == "support":
        existing_admin_reply = query_db("""
            SELECT COUNT(*) as cnt FROM chat_messages
            WHERE room = 'support' AND (session_id = ? OR user_id = ?) AND is_admin = 1
        """, (sid, user_id or "none"), one=True)
        if not existing_admin_reply or existing_admin_reply["cnt"] == 0:
            execute_db("""
                INSERT INTO chat_messages (id, room, user_id, session_id, sender_name, message, is_admin, created_at)
                VALUES (?, 'support', ?, ?, 'Служба поддержки', 'Здравствуйте! Наш менеджер скоро ответит вам.', 1, ?)
            """, (uuid.uuid4().hex, user_id, sid, now_iso()))

    return jsonify({"status": "ok"})


@app.route("/profile")
@app.route("/profile/<user_id>")
@login_required
def profile_view(user_id=None):
    target_id = user_id if user_id else current_user.id
    row = query_db("SELECT * FROM users WHERE id = ?", (target_id,), one=True)
    if not row:
        abort(404)
    profile = dict(row)
    is_self = current_user.id == target_id

    appts_rows = query_db("""
        SELECT a.*, s.title as service_title, sp.name as specialist_name, st.name as station_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN specialists sp ON a.specialist_id = sp.id
        LEFT JOIN stations st ON a.station_id = st.id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
    """, (target_id,))
    appointments = [dict(a) for a in appts_rows]
    spent = query_db("""
        SELECT COALESCE(SUM(s.price), 0) as total FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        WHERE a.user_id = ? AND a.status = 'Готова'
    """, (target_id,), one=True)["total"]
    avg_rating = query_db(
        "SELECT AVG(stars) a FROM reviews WHERE user_id = ?", (target_id,), one=True
    )["a"] or 5.0

    return render_template(
        "profile.html",
        profile=profile,
        is_self=is_self,
        appointments=appointments,
        spent=spent,
        avg_rating=avg_rating,
    )


@app.route("/profile/<user_id>/edit", methods=["GET", "POST"])
@login_required
def profile_edit(user_id):
    if current_user.id != user_id:
        abort(403)

    row = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not row:
        abort(404)
    profile = dict(row)

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        avatar_file = request.files.get("avatar")

        error = None
        if not username or not email:
            error = "Логин и email обязательны."
        else:
            clash = query_db(
                "SELECT id FROM users WHERE LOWER(username) = ? AND id != ?", (username.lower(), user_id), one=True
            )
            if clash:
                error = "Такой логин уже занят."
        if not error:
            clash = query_db(
                "SELECT id FROM users WHERE LOWER(email) = ? AND id != ?", (email.lower(), user_id), one=True
            )
            if clash:
                error = "Этот email уже используется."

        if error:
            flash(error, "error")
            return render_template("profile_edit.html", profile=profile)

        avatar_path = profile.get("avatar")
        saved_path = save_upload(avatar_file, "avatars")
        if saved_path:
            avatar_path = saved_path

        execute_db(
            "UPDATE users SET username = ?, email = ?, phone = ?, avatar = ? WHERE id = ?",
            (username, email, phone, avatar_path, user_id)
        )
        flash("Профиль обновлён.", "success")
        return redirect(url_for("profile_view", user_id=user_id))

    return render_template("profile_edit.html", profile=profile)


@app.route("/profile/<user_id>/toggle-admin", methods=["POST"])
@login_required
@admin_required
def profile_toggle_admin(user_id):
    row = query_db("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if not row:
        abort(404)

    if user_id == current_user.id:
        flash("Нельзя изменить права самому себе.", "error")
        return redirect(url_for("profile_view", user_id=user_id))

    new_admin = 0 if row["is_admin"] else 1
    execute_db("UPDATE users SET is_admin = ? WHERE id = ?", (new_admin, user_id))

    if new_admin:
        flash(f"{row['username']} назначен руководителем.", "success")
    else:
        flash(f"{row['username']} больше не руководитель.", "info")

    return redirect(url_for("profile_view", user_id=user_id))


@app.route("/admin")
@app.route("/admin/dashboard")
@login_required
@admin_required
def admin_dashboard():
    stats = {
        "users": query_db("SELECT COUNT(*) c FROM users", one=True)["c"],
        "services": query_db("SELECT COUNT(*) c FROM services", one=True)["c"],
        "specialists": query_db("SELECT COUNT(*) c FROM specialists", one=True)["c"],
        "stations": query_db("SELECT COUNT(*) c FROM stations", one=True)["c"],
        "appointments": query_db("SELECT COUNT(*) c FROM appointments", one=True)["c"],
        "pending": query_db("SELECT COUNT(*) c FROM appointments WHERE status = 'Ожидает'", one=True)["c"],
        "today": query_db(
            "SELECT COUNT(*) c FROM appointments WHERE date(created_at) = date('now')", one=True
        )["c"],
        "revenue": query_db("""
            SELECT COALESCE(SUM(s.price), 0) r FROM appointments a
            LEFT JOIN services s ON a.service_id = s.id
            WHERE a.status = 'Готова'
        """, one=True)["r"],
    }

    revenue_by_station = [dict(r) for r in query_db("""
        SELECT st.name as station_name, COALESCE(SUM(s.price), 0) as revenue
        FROM stations st
        LEFT JOIN appointments a ON a.station_id = st.id AND a.status = 'Готова'
        LEFT JOIN services s ON a.service_id = s.id
        GROUP BY st.id ORDER BY revenue DESC
    """)]

    services = [dict(s) for s in query_db("SELECT * FROM services ORDER BY created_at DESC")]
    specialists = [dict(sp) for sp in query_db("SELECT * FROM specialists ORDER BY created_at DESC")]
    stations = [dict(s) for s in query_db("SELECT * FROM stations ORDER BY created_at DESC")]

    appointments = [dict(a) for a in query_db("""
        SELECT a.*, s.title as service_title, sp.name as specialist_name, st.name as station_name
        FROM appointments a
        LEFT JOIN services s ON a.service_id = s.id
        LEFT JOIN specialists sp ON a.specialist_id = sp.id
This file is very long (over 20000 tokens). The tool call has been truncated. Please shorten the file content and try again.