import sqlite3
from datetime import datetime
import csv

import os
import sys

def get_database_path():
    if getattr(sys, "frozen", False):
        app_folder = os.path.dirname(sys.executable)
    else:
        app_folder = os.path.dirname(os.path.abspath(__file__))

    data_folder = os.path.join(app_folder, "data")
    os.makedirs(data_folder, exist_ok=True)

    return os.path.join(data_folder, "expenses.db")


db_path = get_database_path()

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    amount REAL NOT NULL,
    category TEXT,
    description TEXT,
    date TEXT NOT NULL
)
""")
conn.commit()
cursor.execute("""
CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    month TEXT NOT NULL,
    amount REAL NOT NULL,
    UNIQUE(category, month)
)
""")

conn.commit()
def add_expense():
    try:
        amount = float(input("Enter expense amount: "))
    except ValueError:
        print("Invalid amount! Please enter a number.")
        return

    if amount <= 0:
        print("Amount must be greater than 0.")
        return

    category = input("Enter category: ")
    description = input("Enter description: ")

    date=datetime.now().strftime("%Y-%m-%d%H:%M:%S")    
    cursor.execute(
        "INSERT INTO transactions (type, amount, category, description,date) VALUES (?, ?, ?, ?,?)",
        ("expense", amount, category, description,date)
    )
    conn.commit()
    print("\nExpense added successfully!")


def add_income():
    try:
        amount = float(input("Enter income amount: "))
    except ValueError:
        print("Invalid amount! Please enter a number.")
        return

    if amount <= 0:
        print("Amount must be greater than 0.")
        return

    category = input("Enter category: ")
    description = input("Enter description: ")
    date=datetime.now().strftime("%Y-%m-%d%H:%M:%S")
    cursor.execute(
        "INSERT INTO transactions (type, amount, category, description,date) VALUES (?, ?, ?, ?,?)",
        ("income", amount, category, description,date)
    )
    conn.commit()
    print("\nIncome added successfully!")

def view_transactions():
    print("\n===== Transactions =====")

    cursor.execute("""
        SELECT id, type, amount, category, description, date
        FROM transactions
    """)

    rows = cursor.fetchall()

    if not rows:
        print("No transactions yet.")
        return

    total_income = 0
    total_expenses = 0

    for row in rows:
        transaction_id, t_type, amount, category, description, date = row

        if t_type == "income":
            total_income += amount
        elif t_type == "expense":
            total_expenses += amount

        print("--------------------")
        print("ID:", transaction_id)
        print("Type:", t_type)
        print("Amount:", amount)
        print("Category:", category)
        print("Description:", description)
        print("Date:", date)

    balance = total_income - total_expenses

    print("====================")
    print("Total Income:", total_income)
    print("Total Expenses:", total_expenses)
    print("Balance:", balance)     

def delete_transaction():
    print("\n===== Delete Transaction =====")

    cursor.execute("""
        SELECT id, type, amount, category, description, date
        FROM transactions
    """)

    rows = cursor.fetchall()

    if not rows:
        print("No transactions to delete.")
        return

    for row in rows:
        transaction_id, t_type, amount, category, description, date = row

        print("--------------------")
        print("ID:", transaction_id)
        print("Type:", t_type)
        print("Amount:", amount)
        print("Category:", category)
        print("Description:", description)
        print("Date:", date)

    print("====================")

    try:
        transaction_id = int(input("Enter transaction ID to delete: "))
    except ValueError:
        print("Invalid ID! Please enter a number.")
        return

    cursor.execute("""
        SELECT id, type, amount, category, description, date
        FROM transactions
        WHERE id = ?
    """, (transaction_id,))

    transaction = cursor.fetchone()

    if not transaction:
        print("Transaction not found.")
        return

    print("\n===== Transaction to Delete =====")
    print("ID:", transaction[0])
    print("Type:", transaction[1])
    print("Amount:", transaction[2])
    print("Category:", transaction[3])
    print("Description:", transaction[4])
    print("Date:", transaction[5])

    confirmation = input(
        "\nAre you sure you want to delete this transaction? (y/n): "
    ).lower()

    if confirmation != "y":
        print("Delete cancelled.")
        return

    cursor.execute(
        "DELETE FROM transactions WHERE id = ?",
        (transaction_id,)
    )

    conn.commit()

    print("\nTransaction deleted successfully!")

def search_transactions():
    print("\n===== Search Transactions =====")
    print("1. Show Expenses")
    print("2. Show Income")
    print("3. Search by Category")

    choice = input("Choose an option: ")

    if choice == "1":
        cursor.execute("""
            SELECT id, type, amount, category, description, date
            FROM transactions
            WHERE type = ?
        """, ("expense",))

    elif choice == "2":
        cursor.execute("""
            SELECT id, type, amount, category, description, date
            FROM transactions
            WHERE type = ?
        """, ("income",))

    elif choice == "3":
        category = input("Enter category: ")

        cursor.execute("""
            SELECT id, type, amount, category, description, date
            FROM transactions
            WHERE category LIKE ?
        """, ("%" + category + "%",))

    else:
        print("Invalid option!")
        return

    rows = cursor.fetchall()

    if not rows:
        print("\nNo transactions found.")
        return

    print("\n===== Results =====")

    for row in rows:
        transaction_id, t_type, amount, category, description, date = row

        print("--------------------")
        print("ID:", transaction_id)
        print("Type:", t_type)
        print("Amount:", amount)
        print("Category:", category)
        print("Description:", description)
        print("Date:", date)

    print("====================")

def statistics():
    print("\n===== Statistics =====")

    cursor.execute("""
        SELECT
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END),
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END)
        FROM transactions
    """)

    result = cursor.fetchone()

    total_income = result[0] or 0
    total_expenses = result[1] or 0
    balance = total_income - total_expenses

    print("Total Income:", total_income)
    print("Total Expenses:", total_expenses)
    print("Balance:", balance)

    cursor.execute("""
        SELECT category, SUM(amount)
        FROM transactions
        WHERE type = 'expense'
        GROUP BY category
        ORDER BY SUM(amount) DESC
    """)

    categories = cursor.fetchall()

    if categories:
        print("\n===== Expenses by Category =====")

        for category, total in categories:
            print(category, ":", total)

        print("\n===== Highest Expense Category =====")
        print("Category:", categories[0][0])
        print("Amount:", categories[0][1])
    else:
        print("\nNo expenses found.")

    cursor.execute("""
        SELECT MAX(amount)
        FROM transactions
        WHERE type = 'expense'
    """)

    highest_expense = cursor.fetchone()[0]

    if highest_expense is not None:
        print("\nHighest Single Expense:", highest_expense)

def edit_transaction():
    print("\n===== Edit Transaction =====")

    cursor.execute("""
        SELECT id, type, amount, category, description, date
        FROM transactions
    """)

    rows = cursor.fetchall()

    if not rows:
        print("No transactions to edit.")
        return

    for row in rows:
        transaction_id, t_type, amount, category, description, date = row

        print("--------------------")
        print("ID:", transaction_id)
        print("Type:", t_type)
        print("Amount:", amount)
        print("Category:", category)
        print("Description:", description)
        print("Date:", date)

    print("====================")

    try:
        transaction_id = int(input("Enter transaction ID to edit: "))
    except ValueError:
        print("Invalid ID! Please enter a number.")
        return

    cursor.execute("""
        SELECT id, type, amount, category, description, date
        FROM transactions
        WHERE id = ?
    """, (transaction_id,))

    transaction = cursor.fetchone()

    if not transaction:
        print("Transaction not found.")
        return

    print("\n===== Current Transaction =====")
    print("ID:", transaction[0])
    print("Type:", transaction[1])
    print("Amount:", transaction[2])
    print("Category:", transaction[3])
    print("Description:", transaction[4])
    print("Date:", transaction[5])

    try:
        new_amount = float(input("Enter new amount: "))
    except ValueError:
        print("Invalid amount! Please enter a number.")
        return

    if new_amount <= 0:
        print("Amount must be greater than 0.")
        return

    new_category = input("Enter new category: ")
    new_description = input("Enter new description: ")

    confirmation = input(
        "\nAre you sure you want to update this transaction? (y/n): "
    ).lower()

    if confirmation != "y":
        print("Edit cancelled.")
        return

    cursor.execute("""
        UPDATE transactions
        SET amount = ?, category = ?, description = ?
        WHERE id = ?
    """, (
        new_amount,
        new_category,
        new_description,
        transaction_id
    ))

    conn.commit()

    print("\nTransaction updated successfully!")

def monthly_summary():
    print("\n===== Monthly Summary =====")

    month = input("Enter month (YYYY-MM): ")

    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        print("Invalid format! Please use YYYY-MM.")
        return

    cursor.execute("""
        SELECT
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END),
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END)
        FROM transactions
        WHERE substr(date, 1, 7) = ?
    """, (month,))

    result = cursor.fetchone()

    total_income = result[0] or 0
    total_expenses = result[1] or 0
    balance = total_income - total_expenses

    print("\n===== Monthly Results =====")
    print("Month:", month)
    print("Total Income:", total_income)
    print("Total Expenses:", total_expenses)
    print("Balance:", balance)

    cursor.execute("""
        SELECT category, SUM(amount)
        FROM transactions
        WHERE type = 'expense'
        AND substr(date, 1, 7) = ?
        GROUP BY category
        ORDER BY SUM(amount) DESC
    """, (month,))

    categories = cursor.fetchall()

    if categories:
        print("\n===== Expenses by Category =====")

        for category, total in categories:
            print(category, ":", total)
    else:
        print("\nNo expenses found for this month.")

def set_budget():
    print("\n===== Set Monthly Budget =====")

    category = input("Enter category: ")
    month = input("Enter month (YYYY-MM): ")

    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        print("Invalid month format! Please use YYYY-MM.")
        return

    try:
        amount = float(input("Enter budget amount: "))
    except ValueError:
        print("Invalid amount! Please enter a number.")
        return

    if amount <= 0:
        print("Budget must be greater than 0.")
        return

    cursor.execute("""
        SELECT id
        FROM budgets
        WHERE category = ? AND month = ?
    """, (category, month))

    existing_budget = cursor.fetchone()

    if existing_budget:
        cursor.execute("""
            UPDATE budgets
            SET amount = ?
            WHERE category = ? AND month = ?
        """, (amount, category, month))

        print("\nBudget updated successfully!")

    else:
        cursor.execute("""
            INSERT INTO budgets (category, month, amount)
            VALUES (?, ?, ?)
        """, (category, month, amount))

        print("\nBudget added successfully!")

    conn.commit()

def view_budgets():
    print("\n===== Monthly Budgets =====")

    month = input("Enter month (YYYY-MM): ")

    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        print("Invalid month format! Please use YYYY-MM.")
        return

    cursor.execute("""
        SELECT category, amount
        FROM budgets
        WHERE month = ?
        ORDER BY category
    """, (month,))

    budgets = cursor.fetchall()

    if not budgets:
        print("No budgets found for this month.")
        return

    for category, budget in budgets:

        cursor.execute("""
            SELECT SUM(amount)
            FROM transactions
            WHERE type = 'expense'
            AND category = ?
            AND substr(date, 1, 7) = ?
        """, (category, month))

        result = cursor.fetchone()

        spent = result[0] or 0
        remaining = budget - spent

        print("--------------------")
        print("Category:", category)
        print("Month:", month)
        print("Budget:", budget)
        print("Spent:", spent)
        print("Remaining:", remaining)

        if remaining < 0:
            print("WARNING: Budget exceeded!")

        elif remaining == 0:
            print("WARNING: Budget fully used!")

        elif spent >= budget * 0.8:
            print("WARNING: You used 80% or more of your budget.")

    print("====================")

def dashboard():
    print("\n===== Dashboard =====")

    # Overall totals
    cursor.execute("""
        SELECT
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END),
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END)
        FROM transactions
    """)

    result = cursor.fetchone()

    total_income = result[0] or 0
    total_expenses = result[1] or 0
    balance = total_income - total_expenses

    print("\n===== Overall =====")
    print("Total Income:", total_income)
    print("Total Expenses:", total_expenses)
    print("Balance:", balance)

    # Current month
    current_month = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END),
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END)
        FROM transactions
        WHERE substr(date, 1, 7) = ?
    """, (current_month,))

    result = cursor.fetchone()

    monthly_income = result[0] or 0
    monthly_expenses = result[1] or 0
    monthly_balance = monthly_income - monthly_expenses

    print("\n===== This Month =====")
    print("Month:", current_month)
    print("Income:", monthly_income)
    print("Expenses:", monthly_expenses)
    print("Balance:", monthly_balance)

    # Top expense category
    cursor.execute("""
        SELECT category, SUM(amount)
        FROM transactions
        WHERE type = 'expense'
        GROUP BY category
        ORDER BY SUM(amount) DESC
        LIMIT 1
    """)

    top_category = cursor.fetchone()

    print("\n===== Top Expense Category =====")

    if top_category:
        print("Category:", top_category[0])
        print("Amount:", top_category[1])
    else:
        print("No expenses found.")

    # Budget status for current month
    cursor.execute("""
        SELECT category, amount
        FROM budgets
        WHERE month = ?
        ORDER BY category
    """, (current_month,))

    budgets = cursor.fetchall()

    print("\n===== Budget Status =====")

    if not budgets:
        print("No budgets set for this month.")

    else:
        for category, budget in budgets:

            cursor.execute("""
                SELECT SUM(amount)
                FROM transactions
                WHERE type = 'expense'
                AND category = ?
                AND substr(date, 1, 7) = ?
            """, (category, current_month))

            result = cursor.fetchone()

            spent = result[0] or 0
            remaining = budget - spent

            print("--------------------")
            print("Category:", category)
            print("Budget:", budget)
            print("Spent:", spent)
            print("Remaining:", remaining)

            if remaining < 0:
                print("Status: OVER BUDGET!")

            elif spent >= budget * 0.8:
                print("Status: WARNING!")

            else:
                print("Status: OK")

    print("\n====================")

def export_transactions():
    print("\n===== Export Transactions =====")

    cursor.execute("""
        SELECT id, type, amount, category, description, date
        FROM transactions
        ORDER BY date
    """)

    rows = cursor.fetchall()

    if not rows:
        print("No transactions to export.")
        return

    filename = "transactions.csv"

    with open(filename, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)

        writer.writerow([
            "ID",
            "Type",
            "Amount",
            "Category",
            "Description",
            "Date"
        ])

        writer.writerows(rows)

    print("\nTransactions exported successfully!")
    print("File:", filename)

def filter_by_date():
    print("\n===== Filter by Date =====")

    start_date = input("Enter start date (YYYY-MM-DD): ")
    end_date = input("Enter end date (YYYY-MM-DD): ")

    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        print("Invalid date format! Please use YYYY-MM-DD.")
        return

    if start_date > end_date:
        print("Start date cannot be after end date.")
        return

    cursor.execute("""
        SELECT id, type, amount, category, description, date
        FROM transactions
        WHERE date >= ?
        AND date < ?
        ORDER BY date
    """, (
        start_date + " 00:00:00",
        end_date + " 23:59:59"
    ))

    rows = cursor.fetchall()

    if not rows:
        print("\nNo transactions found in this date range.")
        return

    print("\n===== Results =====")

    total_income = 0
    total_expenses = 0

    for row in rows:
        transaction_id, t_type, amount, category, description, date = row

        print("--------------------")
        print("ID:", transaction_id)
        print("Type:", t_type)
        print("Amount:", amount)
        print("Category:", category)
        print("Description:", description)
        print("Date:", date)

        if t_type == "income":
            total_income += amount
        else:
            total_expenses += amount

    print("====================")
    print("Total Income:", total_income)
    print("Total Expenses:", total_expenses)
    print("Balance:", total_income - total_expenses)
while True:
    print("=====================")
    print("Qusai's Expense Tracker")
    print("=====================")
    print("1. Add Expense")
    print("2. Add Income")
    print("3. View Transactions")
    print("4. Delete Transactions")
    print("5. Search Transactions")
    print("6. Statistics")
    print("7. Edit Transactions")
    print("8. Sonthly Summary")
    print("9. Set Budget")
    print("10. View Budget")
    print("11. Dashboard")
    print("12. Export Transactions")
    print("13. Filter By Date")
    print("14. Exit")

    choice = input("Choose an option: ")

    if choice == "1":
        add_expense()
    elif choice == "2":
        add_income()
    elif choice == "3":
        view_transactions()
    elif choice =="4":
        delete_transaction()
    elif choice == "5":
        search_transactions() 
    elif choice =="6":
        statistics()
    elif choice == "7":
        edit_transaction()
    elif choice== "8":
        monthly_summary()
    elif choice== "9":
        set_budget()
    elif choice== "10":
        view_budgets()
    elif choice=="11":
        dashboard()
    elif choice== "12":
        export_transactions()
    elif choice=="13":
        filter_by_date()                                             
    elif choice == "14":
        print("Goodbye!")
        conn.close()
        break
    else:
        print("Invalid option!")