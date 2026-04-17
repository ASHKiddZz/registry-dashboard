import sqlite3

conn = sqlite3.connect('registry_database.db')
cursor = conn.cursor()

# This will print every user currently in your system
cursor.execute("SELECT user_id, name, role FROM Users LIMIT 5")
users = cursor.fetchall()

print("--- TOP 5 USERS IN DATABASE ---")
for user in users:
    print(f"ID: {user[0]} | Name: {user[1]} | Role: {user[2]}")

conn.close()