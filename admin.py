from db import get_db

def make_admin(username):
    conn = get_db()
    cur = conn.cursor()
    
    # Обновляем флаг is_admin для указанного пользователя
    cur.execute("UPDATE users SET is_admin = 1 WHERE LOWER(username) = LOWER(?)", (username,))
    conn.commit()
    
    if cur.rowcount > 0:
        print(f"Успешно! Пользователь '{username}' теперь администратор.")
    else:
        print(f"Ошибка: Пользователь с логином '{username}' не найден в базе данных.")
        
    conn.close()

if __name__ == "__main__":
    username_input = input("Введите логин пользователя для выдачи прав админа: ").strip()
    if username_input:
        make_admin(username_input)
    else:
        print("Логин не может быть пустым.")