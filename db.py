import os
import sqlite3
import uuid
from datetime import datetime
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "garage.db")

def get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Пользователи
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        phone TEXT,
        is_admin INTEGER NOT NULL DEFAULT 0,
        avatar TEXT,
        bonus_points INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # СТО / Станции
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stations (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        address TEXT NOT NULL,
        city TEXT NOT NULL,
        created_at TEXT
    )
    """)

    # Услуги
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS services (
        id TEXT PRIMARY KEY,
        category TEXT NOT NULL,
        badge TEXT,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        station_id TEXT,
        price REAL NOT NULL,
        old_price REAL,
        duration_label TEXT,
        rating REAL DEFAULT 5.0,
        reviews INTEGER DEFAULT 0,
        plate TEXT,
        img_variant INTEGER DEFAULT 1,
        image TEXT,
        created_by TEXT,
        created_at TEXT,
        FOREIGN KEY (station_id) REFERENCES stations(id)
    )
    """)

    # Специалисты
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS specialists (
        id TEXT PRIMARY KEY,
        station_id TEXT,
        name TEXT NOT NULL,
        role TEXT NOT NULL,
        photo TEXT,
        rating REAL DEFAULT 5.0,
        experience TEXT,
        phone TEXT,
        status TEXT DEFAULT 'Свободен',
        completed_jobs INTEGER DEFAULT 0,
        earnings REAL DEFAULT 0,
        created_at TEXT,
        FOREIGN KEY (station_id) REFERENCES stations(id)
    )
    """)

    # Записи / Заявки
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS appointments (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        station_id TEXT,
        user_name TEXT NOT NULL,
        user_phone TEXT NOT NULL,
        service_id TEXT,
        specialist_id TEXT,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        car_info TEXT,
        comment TEXT,
        status TEXT NOT NULL DEFAULT 'Ожидает',
        created_at TEXT
    )
    """)

    # Отзывы
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        author_name TEXT NOT NULL,
        service_id TEXT,
        stars INTEGER DEFAULT 5,
        text TEXT NOT NULL,
        created_at TEXT
    )
    """)

    # Уведомления
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        message TEXT NOT NULL,
        ntype TEXT DEFAULT 'info',
        is_read INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # Сообщения в чатах
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id TEXT PRIMARY KEY,
        room TEXT DEFAULT 'support',
        user_id TEXT,
        session_id TEXT,
        sender_name TEXT NOT NULL,
        message TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    conn.commit()
    conn.close()

def seed_db():
    init_db()
    conn = get_db()
    cursor = conn.cursor()

    # Админ по умолчанию
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = '123456'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO users (id, username, email, password_hash, phone, is_admin, avatar, bonus_points, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uuid.uuid4().hex,
            "123456",
            "admin@garage.local",
            generate_password_hash("123456"),
            "+7 (999) 000-00-00",
            1,
            None,
            100,
            datetime.utcnow().isoformat()
        ))

    # Начальные СТО
    cursor.execute("SELECT COUNT(*) FROM stations")
    if cursor.fetchone()[0] == 0:
        st1_id = uuid.uuid4().hex
        st2_id = uuid.uuid4().hex
        cursor.execute("INSERT INTO stations VALUES (?, ?, ?, ?, ?)", 
                       (st1_id, "AUTO•PRO Центр", "ул. Ленина, д. 45", "Москва", datetime.utcnow().isoformat()))
        cursor.execute("INSERT INTO stations VALUES (?, ?, ?, ?, ?)", 
                       (st2_id, "AUTO•PRO Север", "пр. Мира, д. 102", "Москва", datetime.utcnow().isoformat()))
    else:
        st1_id = cursor.execute("SELECT id FROM stations LIMIT 1").fetchone()[0]

    # Начальные услуги
    cursor.execute("SELECT COUNT(*) FROM services")
    if cursor.fetchone()[0] == 0:
        initial_services = [
            ("service", "ТОП", "Комплексное ТО и диагностика", "AUTO•PRO Центр", st1_id, 3500.0, 4200.0, "1-2 часа", 4.9, 28, "A01", 1),
            ("tires", "СКИДКА", "Сезонная переобувка и балансировка", "AUTO•PRO Север", st1_id, 1800.0, 2200.0, "45 мин", 4.8, 45, "B02", 2),
            ("detailing", "НОВИНКА", "Детейлинг и полировка кузова", "Garage Auto Spa", st1_id, 8000.0, None, "4 часа", 5.0, 19, "C03", 3),
            ("dealers", "ТОП", "Подбор и проверка авто перед покупкой", "АвтоДилер Эксперт", st1_id, 5000.0, None, "1 день", 4.9, 62, "D04", 4),
        ]
        for cat, badge, title, company, st_id, price, old_p, dur, rating, reviews, plate, img_var in initial_services:
            cursor.execute("""
                INSERT INTO services (id, category, badge, title, company, station_id, price, old_price, duration_label, rating, reviews, plate, img_variant, image, created_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uuid.uuid4().hex, cat, badge, title, company, st_id, price, old_p, dur, rating, reviews, plate, img_var, None, None, datetime.utcnow().isoformat()
            ))

    # Начальные специалисты
    cursor.execute("SELECT COUNT(*) FROM specialists")
    if cursor.fetchone()[0] == 0:
        seed_specialists = [
            ("Александр Смирнов", "Главный механик и диагност", 4.9, "12 лет", "+7 (999) 111-22-33", st1_id),
            ("Максим Волков", "Мастер по шиномонтажу и сход-развалу", 4.8, "8 лет", "+7 (999) 222-33-44", st1_id),
        ]
        for name, role, rating, exp, phone, st_id in seed_specialists:
            cursor.execute("""
                INSERT INTO specialists (id, station_id, name, role, photo, rating, experience, phone, status, completed_jobs, earnings, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Свободен', 0, 0, ?)
            """, (
                uuid.uuid4().hex, st_id, name, role, None, rating, exp, phone, datetime.utcnow().isoformat()
            ))

    conn.commit()
    conn.close()