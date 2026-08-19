@@
 def index():
@@
     return render_template(
         "index.html",
         categories=CATEGORIES,
         services=services,
         stations=stations,
         stats=stats,
         next_appt=next_appt,
         notifications=notifications,
     )
+
+
+@app.route("/announcements")
+def announcements():
+    # Попытка получить объявления из БД; если таблицы/запроса нет — вернём пустой список,
+    # чтобы не ломать отображение сайта.
+    try:
+        rows = query_db("SELECT * FROM announcements ORDER BY created_at DESC")
+        announcements = [dict(r) for r in rows] if rows else []
+    except Exception:
+        announcements = []
+    return render_template("announcements.html", announcements=announcements, categories=CATEGORIES)
@@
 _ensure_dirs()
 seed_db()
