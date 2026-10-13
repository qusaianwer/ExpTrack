import customtkinter as ctk
import sqlite3
from datetime import datetime, timezone

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ==================================================
# SETTINGS
# ==================================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# DATABASE (Supabase + local in-memory cache)
# ==================================================
#
# All data lives in Supabase (same account as the phone app).
# After login everything is loaded into a small in-memory SQLite
# cache so the screens below can keep using fast local queries.
# Every add / edit / delete is written to Supabase first, then
# mirrored into the cache.

import os
import sys
from pathlib import Path
from tkinter import messagebox

try:
    from supabase import create_client
except ImportError:
    print("Missing package. Run:  pip install supabase")
    sys.exit(1)

SUPABASE_URL = "https://veeyvdfgftgqzypkghmb.supabase.co"
SUPABASE_KEY = "sb_publishable_t19_b1VmzdUmAKYHuZiF0Q__x6OxIUz"

APP_DIR = Path(os.getenv("APPDATA", Path.home())) / "ExpTrack"
APP_DIR.mkdir(parents=True, exist_ok=True)
EMAIL_FILE = APP_DIR / "last_email.txt"

sb = create_client(SUPABASE_URL, SUPABASE_KEY)
current_user_id = None

# In-memory cache (rebuilt from Supabase on every start)
conn = sqlite3.connect(":memory:")
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT,
        type TEXT NOT NULL,
        amount REAL NOT NULL,
        category TEXT,
        description TEXT,
        date TEXT
    )
""")

cursor.execute("""
    CREATE TABLE budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT,
        category TEXT NOT NULL,
        amount REAL NOT NULL,
        month TEXT NOT NULL
    )
""")


def _to_local_str(iso):
    """Supabase timestamp -> local 'YYYY-MM-DD HH:MM:SS'."""
    iso = str(iso).replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _local_str_to_iso(s):
    """Local 'YYYY-MM-DD HH:MM:SS' -> ISO with timezone for Supabase."""
    dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").astimezone()
    return dt.isoformat()


def _fail(action, error):
    messagebox.showerror("ExpTrack", f"Could not {action}.\n\n{error}")
    raise error


def load_cache():
    """Pull all of the user's data from Supabase into the cache."""
    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM budgets")

    rows = []
    start = 0
    while True:
        res = (
            sb.table("transactions")
            .select("id,type,amount,category,description,occurred_at")
            .order("occurred_at")
            .range(start, start + 999)
            .execute()
        )
        rows.extend(res.data)
        if len(res.data) < 1000:
            break
        start += 1000

    for r in rows:
        cursor.execute(
            "INSERT INTO transactions (uid,type,amount,category,description,date)"
            " VALUES (?,?,?,?,?,?)",
            (
                r["id"],
                r["type"],
                float(r["amount"]),
                r.get("category") or "",
                r.get("description") or "",
                _to_local_str(r["occurred_at"]),
            ),
        )

    res = sb.table("budgets").select("id,category,amount,month").execute()
    for b in res.data:
        cursor.execute(
            "INSERT INTO budgets (uid,category,amount,month) VALUES (?,?,?,?)",
            (b["id"], b["category"], float(b["amount"]), str(b["month"])[:7]),
        )
    conn.commit()


def _uid_of(table, local_id):
    cursor.execute(f"SELECT uid FROM {table} WHERE id = ?", (local_id,))
    row = cursor.fetchone()
    return row[0] if row else None


def db_add_transaction(t_type, amount, category, description, date_str):
    try:
        res = sb.table("transactions").insert({
            "user_id": current_user_id,
            "type": t_type,
            "amount": amount,
            "category": category,
            "description": description,
            "occurred_at": _local_str_to_iso(date_str),
        }).execute()
    except Exception as e:
        _fail("save the transaction", e)
    cursor.execute(
        "INSERT INTO transactions (uid,type,amount,category,description,date)"
        " VALUES (?,?,?,?,?,?)",
        (res.data[0]["id"], t_type, amount, category, description, date_str),
    )
    conn.commit()


def db_update_transaction(local_id, t_type, amount, category, description):
    uid = _uid_of("transactions", local_id)
    try:
        sb.table("transactions").update({
            "type": t_type,
            "amount": amount,
            "category": category,
            "description": description,
        }).eq("id", uid).execute()
    except Exception as e:
        _fail("update the transaction", e)
    cursor.execute(
        "UPDATE transactions SET type=?, amount=?, category=?, description=?"
        " WHERE id=?",
        (t_type, amount, category, description, local_id),
    )
    conn.commit()


def db_delete_transaction(local_id):
    uid = _uid_of("transactions", local_id)
    try:
        sb.table("transactions").delete().eq("id", uid).execute()
    except Exception as e:
        _fail("delete the transaction", e)
    cursor.execute("DELETE FROM transactions WHERE id = ?", (local_id,))
    conn.commit()


def db_add_budget(category, amount, month):
    """month is 'YYYY-MM' (stored in Supabase as the 1st of the month)."""
    try:
        res = sb.table("budgets").insert({
            "user_id": current_user_id,
            "category": category,
            "amount": amount,
            "month": month + "-01",
        }).execute()
    except Exception as e:
        _fail("save the budget", e)
    cursor.execute(
        "INSERT INTO budgets (uid,category,amount,month) VALUES (?,?,?,?)",
        (res.data[0]["id"], category, amount, month),
    )
    conn.commit()


# ==================================================
# LOGIN WINDOW (same account as the phone app)
# ==================================================

def run_login():
    global current_user_id

    login = ctk.CTk()
    login.title("ExpTrack - Sign in")
    login.geometry("420x520")
    login.resizable(False, False)

    state = {"ok": False}

    ctk.CTkLabel(
        login, text="ExpTrack",
        font=ctk.CTkFont(size=34, weight="bold"),
        text_color="#3DDC97"
    ).pack(pady=(50, 4))

    ctk.CTkLabel(
        login, text="Sign in with the same account as your phone",
        font=ctk.CTkFont(size=13)
    ).pack(pady=(0, 30))

    email_entry = ctk.CTkEntry(
        login, width=300, height=42, placeholder_text="Email"
    )
    email_entry.pack(pady=8)

    password_entry = ctk.CTkEntry(
        login, width=300, height=42, placeholder_text="Password", show="*"
    )
    password_entry.pack(pady=8)

    msg = ctk.CTkLabel(login, text="", text_color="#E74C3C", wraplength=300)
    msg.pack(pady=8)

    try:
        saved = EMAIL_FILE.read_text(encoding="utf-8").strip()
        if saved:
            email_entry.insert(0, saved)
    except Exception:
        pass

    def finish(user):
        global current_user_id
        current_user_id = user.id
        try:
            EMAIL_FILE.write_text(email_entry.get().strip(), encoding="utf-8")
        except Exception:
            pass
        msg.configure(text="Loading your data...", text_color="#3DDC97")
        login.update()
        try:
            load_cache()
        except Exception as e:
            msg.configure(text=f"Could not load data: {e}", text_color="#E74C3C")
            return
        state["ok"] = True
        login.destroy()

    def do_sign_in(event=None):
        email = email_entry.get().strip()
        password = password_entry.get()
        if not email or not password:
            msg.configure(text="Enter email and password.", text_color="#E74C3C")
            return
        msg.configure(text="Signing in...", text_color="#3DDC97")
        login.update()
        try:
            res = sb.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            finish(res.user)
        except Exception as e:
            msg.configure(text=str(e), text_color="#E74C3C")

    def do_sign_up():
        email = email_entry.get().strip()
        password = password_entry.get()
        if not email or len(password) < 6:
            msg.configure(
                text="Enter email and a password (6+ characters).",
                text_color="#E74C3C"
            )
            return
        try:
            res = sb.auth.sign_up({"email": email, "password": password})
            if res.session is None:
                msg.configure(
                    text="Account created. Confirm your email, then sign in.",
                    text_color="#3DDC97"
                )
            else:
                finish(res.user)
        except Exception as e:
            msg.configure(text=str(e), text_color="#E74C3C")

    ctk.CTkButton(
        login, text="Sign in", width=300, height=44,
        fg_color="#3DDC97", hover_color="#2FB57D", text_color="#0F1A17",
        font=ctk.CTkFont(size=15, weight="bold"),
        command=do_sign_in
    ).pack(pady=(10, 8))

    ctk.CTkButton(
        login, text="Create account", width=300, height=40,
        fg_color="transparent", border_width=1, border_color="#3DDC97",
        text_color="#3DDC97", command=do_sign_up
    ).pack(pady=4)

    password_entry.bind("<Return>", do_sign_in)
    login.protocol("WM_DELETE_WINDOW", login.destroy)
    login.mainloop()

    if not state["ok"]:
        sys.exit(0)


run_login()

# ==================================================
# MAIN WINDOW
# ==================================================

app = ctk.CTk()

app.title("Qusai's Expense Tracker")
app.geometry("1150x720")
app.minsize(950, 600)


# ==================================================
# MATPLOTLIB REFERENCES
# ==================================================

current_figure = None
current_canvas = None


# ==================================================
# HELPERS
# ==================================================

def close_current_chart():

    global current_figure
    global current_canvas

    if current_canvas is not None:

        try:
            current_canvas.get_tk_widget().destroy()
        except Exception:
            pass

        current_canvas = None

    if current_figure is not None:

        try:
            plt.close(current_figure)
        except Exception:
            pass

        current_figure = None


def clear_main_frame():

    close_current_chart()

    for widget in main_frame.winfo_children():

        try:
            widget.destroy()
        except Exception:
            pass


def create_card(parent, title, value):

    # Choose color based on card title
    if title == "Balance":
        accent_color = "#4EA8DE"

    elif title in ["Income", "Total Income"]:
        accent_color = "#2FA572"

    elif title in ["Expenses", "Total Expenses"]:
        accent_color = "#E74C3C"

    else:
        accent_color = "#4EA8DE"

    card = ctk.CTkFrame(
        parent,
        corner_radius=18,
        fg_color="#1E1E1E"
    )

    card.pack(
        side="left",
        fill="both",
        expand=True,
        padx=7
    )

    # Accent line
    ctk.CTkFrame(
        card,
        height=5,
        corner_radius=5,
        fg_color=accent_color
    ).pack(
        fill="x",
        padx=18,
        pady=(15, 0)
    )

    # Title
    ctk.CTkLabel(
        card,
        text=title,
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        ),
        text_color="#AAAAAA"
    ).pack(
        anchor="w",
        padx=20,
        pady=(18, 5)
    )

    # Amount
    ctk.CTkLabel(
        card,
        text=value,
        font=ctk.CTkFont(
            size=26,
            weight="bold"
        ),
        text_color="#FFFFFF"
    ).pack(
        anchor="w",
        padx=20,
        pady=(0, 20)
    )

    return card


# ==================================================
# DASHBOARD
# ==================================================

def show_dashboard():

    clear_main_frame()

    ctk.CTkLabel(
        main_frame,
        text="Dashboard",
        font=ctk.CTkFont(
            size=32,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(35, 5)
    )

    ctk.CTkLabel(
        main_frame,
        text="Overview of your financial activity",
        font=ctk.CTkFont(size=15)
    ).pack(
        anchor="w",
        padx=40,
        pady=(0, 25)
    )

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

    cards_frame = ctk.CTkFrame(
        main_frame,
        fg_color="transparent"
    )

    cards_frame.pack(
        fill="x",
        padx=33
    )

    create_card(
        cards_frame,
        "Balance",
        f"{balance:.2f} JOD"
    )

    create_card(
        cards_frame,
        "Total Income",
        f"{total_income:.2f} JOD"
    )

    create_card(
        cards_frame,
        "Total Expenses",
        f"{total_expenses:.2f} JOD"
    )

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

    monthly_balance = (
        monthly_income - monthly_expenses
    )

    month_frame = ctk.CTkFrame(
        main_frame,
        corner_radius=15
    )

    month_frame.pack(
        fill="x",
        padx=40,
        pady=30
    )

    ctk.CTkLabel(
        month_frame,
        text=f"This Month — {current_month}",
        font=ctk.CTkFont(
            size=21,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=25,
        pady=(20, 15)
    )

    ctk.CTkLabel(
        month_frame,
        text=(
            f"Income: {monthly_income:.2f} JOD\n"
            f"Expenses: {monthly_expenses:.2f} JOD\n"
            f"Balance: {monthly_balance:.2f} JOD"
        ),
        justify="left",
        font=ctk.CTkFont(size=16)
    ).pack(
        anchor="w",
        padx=25,
        pady=(0, 20)
    )
    # ==================================================
    # RECENT TRANSACTIONS
    # ==================================================

    ctk.CTkLabel(
        main_frame,
        text="Recent Transactions",
        font=ctk.CTkFont(
            size=21,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(5, 12)
    )

    recent_frame = ctk.CTkFrame(
        main_frame,
        corner_radius=15
    )

    recent_frame.pack(
        fill="x",
        padx=40,
        pady=(0, 25)
    )

    cursor.execute("""
        SELECT type, amount, category, date
        FROM transactions
        ORDER BY id DESC
        LIMIT 5
    """)

    recent_transactions = cursor.fetchall()

    if not recent_transactions:

        ctk.CTkLabel(
            recent_frame,
            text="No transactions yet.",
            text_color="#888888",
            font=ctk.CTkFont(size=14)
        ).pack(
            pady=25
        )

    else:

        for t_type, amount, category, date in recent_transactions:

            if t_type == "expense":
                color = "#E74C3C"
                sign = "-"
            else:
                color = "#2FA572"
                sign = "+"

            row = ctk.CTkFrame(
                recent_frame,
                fg_color="transparent"
            )

            row.pack(
                fill="x",
                padx=20,
                pady=8
            )

            # Category
            ctk.CTkLabel(
                row,
                text=category or "Uncategorized",
                font=ctk.CTkFont(
                    size=14,
                    weight="bold"
                )
            ).pack(
                side="left"
            )

            # Date
            ctk.CTkLabel(
                row,
                text=date,
                text_color="#777777",
                font=ctk.CTkFont(size=12)
            ).pack(
                side="left",
                padx=20
            )

            # Amount
            ctk.CTkLabel(
                row,
                text=f"{sign}{amount:.2f} JOD",
                text_color=color,
                font=ctk.CTkFont(
                    size=14,
                    weight="bold"
                )
            ).pack(
                side="right"
            )
            # ==================================================
    # VIEW ALL TRANSACTIONS BUTTON
    # ==================================================

    ctk.CTkButton(
        main_frame,
        text="View All Transactions",
        height=42,
        corner_radius=10,
        fg_color="#2B6CB0",
        hover_color="#245A91",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        ),
        command=show_transactions
    ).pack(
        padx=40,
        pady=(0, 25),
        fill="x"
    )    

# ==================================================
# ADD EXPENSE / ADD INCOME
# ==================================================

def show_add_transaction(transaction_type):

    clear_main_frame()

    # ==================================================
    # SETTINGS
    # ==================================================

    if transaction_type == "expense":
        title = "Add Expense"
        accent_color = "#E74C3C"
        button_color = "#C0392B"
        hover_color = "#962D22"
    else:
        title = "Add Income"
        accent_color = "#2FA572"
        button_color = "#23865A"
        hover_color = "#1C6B48"

    # ==================================================
    # HEADER
    # ==================================================

    ctk.CTkLabel(
        main_frame,
        text=title,
        font=ctk.CTkFont(
            size=32,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(35, 5)
    )

    ctk.CTkLabel(
        main_frame,
        text="Enter the transaction details below",
        text_color="#888888",
        font=ctk.CTkFont(size=14)
    ).pack(
        anchor="w",
        padx=40,
        pady=(0, 25)
    )

    # ==================================================
    # FORM
    # ==================================================

    form = ctk.CTkFrame(
        main_frame,
        corner_radius=18,
        fg_color="#1E1E1E"
    )

    form.pack(
        padx=40,
        pady=5,
        fill="x"
    )

    # Accent line
    ctk.CTkFrame(
        form,
        height=5,
        corner_radius=5,
        fg_color=accent_color
    ).pack(
        fill="x",
        padx=20,
        pady=(18, 5)
    )

    # ==================================================
    # AMOUNT
    # ==================================================

    ctk.CTkLabel(
        form,
        text="Amount",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=25,
        pady=(20, 5)
    )

    amount_entry = ctk.CTkEntry(
        form,
        placeholder_text="Enter amount in JOD",
        height=42,
        corner_radius=10
    )

    amount_entry.pack(
        fill="x",
        padx=25
    )

    # ==================================================
    # CATEGORY
    # ==================================================

    ctk.CTkLabel(
        form,
        text="Category",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=25,
        pady=(18, 5)
    )

    category_entry = ctk.CTkEntry(
        form,
        placeholder_text="Food, Transport, Bills...",
        height=42,
        corner_radius=10
    )

    category_entry.pack(
        fill="x",
        padx=25
    )

    # ==================================================
    # DESCRIPTION
    # ==================================================

    ctk.CTkLabel(
        form,
        text="Description",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=25,
        pady=(18, 5)
    )

    description_entry = ctk.CTkEntry(
        form,
        placeholder_text="Optional description",
        height=42,
        corner_radius=10
    )

    description_entry.pack(
        fill="x",
        padx=25
    )

    # ==================================================
    # MESSAGE
    # ==================================================

    message = ctk.CTkLabel(
        form,
        text="",
        font=ctk.CTkFont(size=13)
    )

    message.pack(
        pady=(15, 5)
    )

    # ==================================================
    # SAVE FUNCTION
    # ==================================================

    def save_transaction():

        amount_text = amount_entry.get().strip()
        category = category_entry.get().strip()
        description = description_entry.get().strip()

        try:
            amount = float(amount_text)

        except ValueError:

            message.configure(
                text="Invalid amount! Please enter a number.",
                text_color="#E74C3C"
            )

            return

        if amount <= 0:

            message.configure(
                text="Amount must be greater than 0.",
                text_color="#E74C3C"
            )

            return

        if not category:

            message.configure(
                text="Please enter a category.",
                text_color="#E74C3C"
            )

            return

        current_date = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        db_add_transaction(
            transaction_type,
            amount,
            category,
            description,
            current_date
        )

        message.configure(
            text=f"{title} added successfully!",
            text_color=accent_color
        )

        amount_entry.delete(
            0,
            "end"
        )

        category_entry.delete(
            0,
            "end"
        )

        description_entry.delete(
            0,
            "end"
        )

        amount_entry.focus()

    # ==================================================
    # SAVE BUTTON
    # ==================================================

    ctk.CTkButton(
        form,
        text=f"Save {title}",
        height=45,
        corner_radius=10,
        fg_color=button_color,
        hover_color=hover_color,
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        ),
        command=save_transaction
    ).pack(
        fill="x",
        padx=25,
        pady=(10, 25)
    )

# ==================================================
# EDIT TRANSACTION
# ==================================================

def edit_transaction(transaction_id):

    cursor.execute("""
        SELECT
            type,
            amount,
            category,
            description
        FROM transactions
        WHERE id = ?
    """, (transaction_id,))

    transaction = cursor.fetchone()

    if not transaction:
        return

    old_type, old_amount, old_category, old_description = transaction

    window = ctk.CTkToplevel(app)

    window.title("Edit Transaction")
    window.geometry("500x560")
    window.resizable(False, False)

    window.transient(app)
    window.grab_set()

    ctk.CTkLabel(
        window,
        text="Edit Transaction",
        font=ctk.CTkFont(
            size=26,
            weight="bold"
        )
    ).pack(
        pady=(30, 25)
    )

    ctk.CTkLabel(
        window,
        text="Type"
    ).pack(
        anchor="w",
        padx=40,
        pady=(5, 5)
    )

    type_menu = ctk.CTkOptionMenu(
        window,
        values=[
            "expense",
            "income"
        ]
    )

    type_menu.pack(
        fill="x",
        padx=40
    )

    type_menu.set(old_type)

    ctk.CTkLabel(
        window,
        text="Amount"
    ).pack(
        anchor="w",
        padx=40,
        pady=(15, 5)
    )

    amount_entry = ctk.CTkEntry(
        window,
        height=40
    )

    amount_entry.pack(
        fill="x",
        padx=40
    )

    amount_entry.insert(
        0,
        str(old_amount)
    )

    ctk.CTkLabel(
        window,
        text="Category"
    ).pack(
        anchor="w",
        padx=40,
        pady=(15, 5)
    )

    category_entry = ctk.CTkEntry(
        window,
        height=40
    )

    category_entry.pack(
        fill="x",
        padx=40
    )

    category_entry.insert(
        0,
        old_category or ""
    )

    ctk.CTkLabel(
        window,
        text="Description"
    ).pack(
        anchor="w",
        padx=40,
        pady=(15, 5)
    )

    description_entry = ctk.CTkEntry(
        window,
        height=40
    )

    description_entry.pack(
        fill="x",
        padx=40
    )

    description_entry.insert(
        0,
        old_description or ""
    )

    message = ctk.CTkLabel(
        window,
        text=""
    )

    message.pack(
        pady=12
    )

    def save_changes():

        try:

            amount = float(
                amount_entry.get().strip()
            )

        except ValueError:

            message.configure(
                text="Invalid amount!",
                text_color="#E74C3C"
            )

            return

        if amount <= 0:

            message.configure(
                text="Amount must be greater than 0.",
                text_color="#E74C3C"
            )

            return

        category = category_entry.get().strip()
        description = description_entry.get().strip()
        transaction_type = type_menu.get()

        if not category:

            message.configure(
                text="Please enter a category.",
                text_color="#E74C3C"
            )

            return

        db_update_transaction(
            transaction_id,
            transaction_type,
            amount,
            category,
            description
        )

        window.destroy()

        show_transactions()

    ctk.CTkButton(
        window,
        text="Save Changes",
        height=45,
        command=save_changes
    ).pack(
        fill="x",
        padx=40,
        pady=(5, 20)
    )


# ==================================================
# DELETE TRANSACTION
# ==================================================

def delete_transaction(transaction_id):

    confirmation = ctk.CTkToplevel(app)

    confirmation.title("Confirm Delete")
    confirmation.geometry("400x220")
    confirmation.resizable(False, False)

    confirmation.transient(app)
    confirmation.grab_set()

    ctk.CTkLabel(
        confirmation,
        text="Delete Transaction?",
        font=ctk.CTkFont(
            size=22,
            weight="bold"
        )
    ).pack(
        pady=(30, 10)
    )

    ctk.CTkLabel(
        confirmation,
        text="This action cannot be undone.",
        font=ctk.CTkFont(size=14)
    ).pack(
        pady=(0, 20)
    )

    buttons_frame = ctk.CTkFrame(
        confirmation,
        fg_color="transparent"
    )

    buttons_frame.pack(
        fill="x",
        padx=30
    )

    def confirm_delete():

        db_delete_transaction(transaction_id)

        confirmation.destroy()

        show_transactions()

    ctk.CTkButton(
        buttons_frame,
        text="Delete",
        fg_color="#C0392B",
        hover_color="#962D22",
        command=confirm_delete
    ).pack(
        side="left",
        expand=True,
        padx=5
    )

    ctk.CTkButton(
        buttons_frame,
        text="Cancel",
        command=confirmation.destroy
    ).pack(
        side="right",
        expand=True,
        padx=5
    )


# ==================================================
# TRANSACTION CARD
# ==================================================

def create_transaction_card(parent, row):

    transaction_id, t_type, amount, category, description, date = row

    # ==================================================
    # COLORS
    # ==================================================

    if t_type == "expense":
        type_text = "EXPENSE"
        type_color = "#E74C3C"
        amount_color = "#E74C3C"
        sign = "-"
    else:
        type_text = "INCOME"
        type_color = "#2FA572"
        amount_color = "#2FA572"
        sign = "+"

    # ==================================================
    # MAIN CARD
    # ==================================================

    item = ctk.CTkFrame(
        parent,
        corner_radius=15,
        fg_color="#1E1E1E"
    )

    item.pack(
        fill="x",
        pady=6
    )

    # ==================================================
    # LEFT SIDE
    # ==================================================

    info_frame = ctk.CTkFrame(
        item,
        fg_color="transparent"
    )

    info_frame.pack(
        side="left",
        fill="both",
        expand=True,
        padx=20,
        pady=15
    )

    # Type
    ctk.CTkLabel(
        info_frame,
        text=type_text,
        text_color=type_color,
        font=ctk.CTkFont(
            size=12,
            weight="bold"
        )
    ).pack(
        anchor="w"
    )

    # Category
    ctk.CTkLabel(
        info_frame,
        text=category or "Uncategorized",
        font=ctk.CTkFont(
            size=18,
            weight="bold"
        ),
        text_color="#FFFFFF"
    ).pack(
        anchor="w",
        pady=(3, 2)
    )

    # Description
    ctk.CTkLabel(
        info_frame,
        text=description or "No description",
        text_color="#AAAAAA",
        font=ctk.CTkFont(
            size=13
        )
    ).pack(
        anchor="w"
    )

    # Date
    ctk.CTkLabel(
        info_frame,
        text=f"📅 {date}",
        text_color="#777777",
        font=ctk.CTkFont(
            size=12
        )
    ).pack(
        anchor="w",
        pady=(5, 0)
    )

    # ==================================================
    # RIGHT SIDE
    # ==================================================

    right_frame = ctk.CTkFrame(
        item,
        fg_color="transparent"
    )

    right_frame.pack(
        side="right",
        padx=20,
        pady=15
    )

    # Amount
    ctk.CTkLabel(
        right_frame,
        text=f"{sign}{amount:.2f} JOD",
        text_color=amount_color,
        font=ctk.CTkFont(
            size=19,
            weight="bold"
        )
    ).pack(
        pady=(0, 10)
    )

    # Buttons
    buttons_frame = ctk.CTkFrame(
        right_frame,
        fg_color="transparent"
    )

    buttons_frame.pack()

    # Edit
    ctk.CTkButton(
        buttons_frame,
        text="Edit",
        width=75,
        height=32,
        corner_radius=8,
        fg_color="#2B6CB0",
        hover_color="#245A91",
        font=ctk.CTkFont(
            size=12,
            weight="bold"
        ),
        command=lambda transaction_id=transaction_id:
            edit_transaction(transaction_id)
    ).pack(
        side="left",
        padx=3
    )

    # Delete
    ctk.CTkButton(
        buttons_frame,
        text="Delete",
        width=75,
        height=32,
        corner_radius=8,
        fg_color="#C0392B",
        hover_color="#962D22",
        font=ctk.CTkFont(
            size=12,
            weight="bold"
        ),
        command=lambda transaction_id=transaction_id:
            delete_transaction(transaction_id)
    ).pack(
        side="left",
        padx=3
    )

# ==================================================
# TRANSACTIONS
# ==================================================

def show_transactions():

    clear_main_frame()

    ctk.CTkLabel(
        main_frame,
        text="Transactions",
        font=ctk.CTkFont(
            size=32,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(35, 20)
    )

    search_frame = ctk.CTkFrame(
        main_frame,
        fg_color="transparent"
    )

    search_frame.pack(
        fill="x",
        padx=40,
        pady=(0, 15)
    )

    search_entry = ctk.CTkEntry(
    search_frame,
    placeholder_text="🔎  Search category or description...",
    height=42,
    corner_radius=10,
    border_width=1,
    border_color="#333333"
        )

    filter_menu = ctk.CTkOptionMenu(
    search_frame,
    values=[
        "All",
        "Income",
        "Expense"
    ],
    width=150,
    height=42,
    corner_radius=10,
    fg_color="#1E1E1E",
    button_color="#2B6CB0",
    button_hover_color="#245A91",
    font=ctk.CTkFont(
        size=13,
        weight="bold"
    )
)

    filter_menu.pack(
    side="right"
)

    filter_menu.set("All")

    results_frame = ctk.CTkScrollableFrame(
        main_frame
    )

    results_frame.pack(
        fill="both",
        expand=True,
        padx=40,
        pady=(0, 30)
    )

    def load_transactions():

        if not results_frame.winfo_exists():
            return

        for widget in results_frame.winfo_children():

            try:
                widget.destroy()
            except Exception:
                pass

        search_text = (
            search_entry.get().strip().lower()
        )

        selected_filter = filter_menu.get()

        cursor.execute("""
            SELECT
                id,
                type,
                amount,
                category,
                description,
                date
            FROM transactions
            ORDER BY id DESC
        """)

        rows = cursor.fetchall()

        filtered_rows = []

        for row in rows:

            transaction_id, t_type, amount, category, description, date = row

            if (
                selected_filter == "Income"
                and t_type != "income"
            ):
                continue

            if (
                selected_filter == "Expense"
                and t_type != "expense"
            ):
                continue

            searchable_text = (
                f"{category or ''} "
                f"{description or ''}"
            ).lower()

            if (
                search_text
                and search_text not in searchable_text
            ):
                continue

            filtered_rows.append(row)

        if not filtered_rows:

            ctk.CTkLabel(
                results_frame,
                text="No transactions found.",
                font=ctk.CTkFont(size=18)
            ).pack(
                pady=40
            )

            return

        for row in filtered_rows:

            create_transaction_card(
                results_frame,
                row
            )

    search_entry.bind(
        "<KeyRelease>",
        lambda event: load_transactions()
    )

    filter_menu.configure(
        command=lambda value: load_transactions()
    )

    load_transactions()
# ==================================================
# ADD BUDGET WINDOW
# ==================================================

def add_budget_window():

    window = ctk.CTkToplevel(app)

    window.title("Add Budget")
    window.geometry("450x430")
    window.resizable(False, False)
    window.transient(app)
    window.grab_set()

    # ==================================================
    # TITLE
    # ==================================================

    ctk.CTkLabel(
        window,
        text="Add Budget",
        font=ctk.CTkFont(
            size=26,
            weight="bold"
        )
    ).pack(
        pady=(30, 5)
    )

    ctk.CTkLabel(
        window,
        text="Set a spending limit for a category",
        text_color="#888888",
        font=ctk.CTkFont(size=13)
    ).pack(
        pady=(0, 20)
    )

    # ==================================================
    # CATEGORY
    # ==================================================

    ctk.CTkLabel(
        window,
        text="Category",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(5, 5)
    )

    category_entry = ctk.CTkEntry(
        window,
        placeholder_text="Food, Transport, Bills...",
        height=42,
        corner_radius=10
    )

    category_entry.pack(
        fill="x",
        padx=40
    )

    # ==================================================
    # AMOUNT
    # ==================================================

    ctk.CTkLabel(
        window,
        text="Budget Amount",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(18, 5)
    )

    amount_entry = ctk.CTkEntry(
        window,
        placeholder_text="Enter budget amount",
        height=42,
        corner_radius=10
    )

    amount_entry.pack(
        fill="x",
        padx=40
    )

    # ==================================================
    # MESSAGE
    # ==================================================

    message = ctk.CTkLabel(
        window,
        text="",
        font=ctk.CTkFont(size=13)
    )

    message.pack(
        pady=15
    )

    # ==================================================
    # SAVE BUDGET
    # ==================================================

    def save_budget():

        category = category_entry.get().strip()
        amount_text = amount_entry.get().strip()

        if not category:

            message.configure(
                text="Please enter a category.",
                text_color="#E74C3C"
            )

            return

        try:
            amount = float(amount_text)

        except ValueError:

            message.configure(
                text="Invalid amount!",
                text_color="#E74C3C"
            )

            return

        if amount <= 0:

            message.configure(
                text="Amount must be greater than 0.",
                text_color="#E74C3C"
            )

            return

        current_month = datetime.now().strftime("%Y-%m")

        # Check if budget already exists
        cursor.execute(
            """
            SELECT id
            FROM budgets
            WHERE category = ?
            AND month = ?
            """,
            (
                category,
                current_month
            )
        )

        existing_budget = cursor.fetchone()

        if existing_budget:

            message.configure(
                text="A budget already exists for this category.",
                text_color="#E74C3C"
            )

            return

        db_add_budget(category, amount, current_month)

        message.configure(
            text="Budget added successfully!",
            text_color="#2FA572"
        )

        category_entry.delete(
            0,
            "end"
        )

        amount_entry.delete(
            0,
            "end"
        )

        # Refresh budgets page
        app.after(
            800,
            lambda: (
                window.destroy(),
                show_budgets()
            )
        )

    # ==================================================
    # BUTTON
    # ==================================================

    ctk.CTkButton(
        window,
        text="Save Budget",
        height=45,
        corner_radius=10,
        fg_color="#2B6CB0",
        hover_color="#245A91",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        ),
        command=save_budget
    ).pack(
        fill="x",
        padx=40,
        pady=(5, 25)
    )

    category_entry.focus()

# ==================================================
# BUDGETS
# ==================================================

def show_budgets():

    clear_main_frame()

    ctk.CTkLabel(
        main_frame,
        text="Budgets",
        font=ctk.CTkFont(
            size=32,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(35, 20)
    )

    current_month = datetime.now().strftime("%Y-%m")

    ctk.CTkLabel(
        main_frame,
        text=f"Current Month: {current_month}",
        font=ctk.CTkFont(size=16)
    ).pack(
        anchor="w",
        padx=40,
        pady=(0, 15)
    )
        # ==================================================
    # ADD BUDGET BUTTON
    # ==================================================

    ctk.CTkButton(
        main_frame,
        text="+ Add Budget",
        height=42,
        width=150,
        corner_radius=10,
        fg_color="#2B6CB0",
        hover_color="#245A91",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        ),
        command=lambda: add_budget_window()
    ).pack(
        anchor="e",
        padx=40,
        pady=(0, 15)
    )

    scroll_frame = ctk.CTkScrollableFrame(
        main_frame
    )

    scroll_frame.pack(
        fill="both",
        expand=True,
        padx=40,
        pady=(0, 30)
    )

    cursor.execute("""
        SELECT category, amount
        FROM budgets
        WHERE month = ?
        ORDER BY category
    """, (current_month,))

    budgets = cursor.fetchall()

    if not budgets:

        ctk.CTkLabel(
            scroll_frame,
            text="No budgets set for this month.",
            font=ctk.CTkFont(size=18)
        ).pack(
            pady=40
        )

        return

    for category, budget in budgets:

        # ==================================================
        # CALCULATE SPENDING
        # ==================================================

        cursor.execute("""
            SELECT SUM(amount)
            FROM transactions
            WHERE type = 'expense'
            AND category = ?
            AND substr(date, 1, 7) = ?
        """, (category, current_month))

        spent = cursor.fetchone()[0] or 0

        remaining = budget - spent

        # ==================================================
        # CALCULATE PROGRESS
        # ==================================================

        if budget > 0:
            progress = spent / budget
        else:
            progress = 0

        # Keep progress between 0 and 1
        progress_display = min(progress, 1)

        # ==================================================
        # COLORS
        # ==================================================

        if spent > budget:
            progress_color = "#E74C3C"
            status_text = "Over Budget"
            status_color = "#E74C3C"

        elif progress >= 0.8:
            progress_color = "#F39C12"
            status_text = "Almost Limit"
            status_color = "#F39C12"

        else:
            progress_color = "#2FA572"
            status_text = "On Track"
            status_color = "#2FA572"

        # ==================================================
        # BUDGET CARD
        # ==================================================

        item = ctk.CTkFrame(
            scroll_frame,
            corner_radius=15,
            fg_color="#1E1E1E"
        )

        item.pack(
            fill="x",
            pady=7
        )

        # ==================================================
        # TOP ROW
        # ==================================================

        top_frame = ctk.CTkFrame(
            item,
            fg_color="transparent"
        )

        top_frame.pack(
            fill="x",
            padx=20,
            pady=(18, 5)
        )

        ctk.CTkLabel(
            top_frame,
            text=category,
            font=ctk.CTkFont(
                size=18,
                weight="bold"
            )
        ).pack(
            side="left"
        )

        ctk.CTkLabel(
            top_frame,
            text=status_text,
            text_color=status_color,
            font=ctk.CTkFont(
                size=12,
                weight="bold"
            )
        ).pack(
            side="right"
        )

        # ==================================================
        # AMOUNTS
        # ==================================================

        ctk.CTkLabel(
            item,
            text=(
                f"Spent: {spent:.2f} JOD    "
                f"of    {budget:.2f} JOD"
            ),
            font=ctk.CTkFont(
                size=14
            ),
            text_color="#BBBBBB"
        ).pack(
            anchor="w",
            padx=20,
            pady=(5, 10)
        )

        # ==================================================
        # PROGRESS BAR
        # ==================================================

        progress_bar = ctk.CTkProgressBar(
            item,
            height=12,
            corner_radius=6,
            progress_color=progress_color
        )

        progress_bar.pack(
            fill="x",
            padx=20,
            pady=(0, 10)
        )

        progress_bar.set(
            progress_display
        )

        # ==================================================
        # BOTTOM ROW
        # ==================================================

        bottom_frame = ctk.CTkFrame(
            item,
            fg_color="transparent"
        )

        bottom_frame.pack(
            fill="x",
            padx=20,
            pady=(0, 18)
        )

        if remaining >= 0:

            remaining_text = (
                f"Remaining: {remaining:.2f} JOD"
            )

            remaining_color = "#2FA572"

        else:

            remaining_text = (
                f"Exceeded by: {abs(remaining):.2f} JOD"
            )

            remaining_color = "#E74C3C"

        ctk.CTkLabel(
            bottom_frame,
            text=remaining_text,
            text_color=remaining_color,
            font=ctk.CTkFont(
                size=13,
                weight="bold"
            )
        ).pack(
            side="left"
        )

        ctk.CTkLabel(
            bottom_frame,
            text=f"{progress * 100:.1f}%",
            text_color="#888888",
            font=ctk.CTkFont(size=12)
        ).pack(
            side="right"
        )


# ==================================================
# STATISTICS + CHARTS
# ==================================================

def show_statistics():

    global current_figure
    global current_canvas

    clear_main_frame()

    ctk.CTkLabel(
        main_frame,
        text="Statistics",
        font=ctk.CTkFont(
            size=32,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=40,
        pady=(30, 20)
    )

    cursor.execute("""
        SELECT
            SUM(
                CASE
                    WHEN type = 'income'
                    THEN amount
                    ELSE 0
                END
            ),
            SUM(
                CASE
                    WHEN type = 'expense'
                    THEN amount
                    ELSE 0
                END
            )
        FROM transactions
    """)

    result = cursor.fetchone()

    income = result[0] or 0
    expenses = result[1] or 0
    balance = income - expenses
        # ==================================================
    # CURRENT MONTH STATISTICS
    # ==================================================

    current_month = datetime.now().strftime("%Y-%m")

    cursor.execute("""
        SELECT
            SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END),
            SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END)
        FROM transactions
        WHERE substr(date, 1, 7) = ?
    """, (current_month,))

    month_result = cursor.fetchone()

    monthly_income = month_result[0] or 0
    monthly_expenses = month_result[1] or 0
    monthly_balance = monthly_income - monthly_expenses

    cards_frame = ctk.CTkFrame(
        main_frame,
        fg_color="transparent"
    )

    cards_frame.pack(
        fill="x",
        padx=33
    )

    create_card(
        cards_frame,
        "Income",
        f"{income:.2f} JOD"
    )

    create_card(
        cards_frame,
        "Expenses",
        f"{expenses:.2f} JOD"
    )

    create_card(
        cards_frame,
        "Balance",
        f"{balance:.2f} JOD"
    )
        # ==================================================
    # MONTHLY SUMMARY
    # ==================================================

    monthly_frame = ctk.CTkFrame(
        main_frame,
        corner_radius=15,
        fg_color="#1E1E1E"
    )

    monthly_frame.pack(
        fill="x",
        padx=40,
        pady=(15, 5)
    )

    ctk.CTkLabel(
        monthly_frame,
        text=f"This Month — {current_month}",
        font=ctk.CTkFont(
            size=19,
            weight="bold"
        )
    ).pack(
        anchor="w",
        padx=20,
        pady=(15, 10)
    )

    ctk.CTkLabel(
        monthly_frame,
        text=(
            f"Income: {monthly_income:.2f} JOD     "
            f"Expenses: {monthly_expenses:.2f} JOD     "
            f"Balance: {monthly_balance:.2f} JOD"
        ),
        text_color="#BBBBBB",
        font=ctk.CTkFont(size=14)
    ).pack(
        anchor="w",
        padx=20,
        pady=(0, 15)
    )

    charts_frame = ctk.CTkFrame(
        main_frame,
        fg_color="transparent"
    )

    charts_frame.pack(
        fill="both",
        expand=True,
        padx=40,
        pady=20
    )

    cursor.execute("""
        SELECT
            category,
            SUM(amount)
        FROM transactions
        WHERE type = 'expense'
        GROUP BY category
        ORDER BY SUM(amount) DESC
    """)

    categories = cursor.fetchall()

    # Create Matplotlib figure

    figure, axes = plt.subplots(
        1,
        2,
        figsize=(10, 4)
    )

    current_figure = figure

    figure.patch.set_facecolor("#2b2b2b")

    # ==================================================
    # PIE CHART
    # ==================================================

    pie_ax = axes[0]

    pie_ax.set_facecolor("#2b2b2b")

    if categories:

        labels = [
            category or "Uncategorized"
            for category, total in categories
        ]

        values = [
            total
            for category, total in categories
        ]

        pie_ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            startangle=90,
            textprops={
                "color": "white"
            }
        )

    else:

        pie_ax.text(
            0.5,
            0.5,
            "No expense data",
            ha="center",
            va="center",
            color="white",
            fontsize=14
        )

    pie_ax.set_title(
        "Expenses by Category",
        color="white"
    )

    # ==================================================
    # BAR CHART
    # ==================================================

    bar_ax = axes[1]

    bar_ax.set_facecolor("#2b2b2b")

    names = [
        "Income",
        "Expenses"
    ]

    values = [
        income,
        expenses
    ]

    colors = [
        "#2FA572",
        "#E74C3C"
    ]

    bars = bar_ax.bar(
        names,
        values,
        color=colors
    )

    bar_ax.set_title(
        "Income vs Expenses",
        color="white"
    )

    bar_ax.tick_params(
        colors="white"
    )

    for spine in bar_ax.spines.values():

        spine.set_color("#555555")

    for bar in bars:

        height = bar.get_height()

        bar_ax.text(
            bar.get_x()
            + bar.get_width() / 2,
            height,
            f"{height:.2f}",
            ha="center",
            va="bottom",
            color="white"
        )

    figure.tight_layout()

    # ==================================================
    # EMBED CHART
    # ==================================================

    current_canvas = FigureCanvasTkAgg(
        figure,
        master=charts_frame
    )

    current_canvas.draw()

    current_canvas.get_tk_widget().pack(
        fill="both",
        expand=True
    )


# ==================================================
# SIDEBAR
# ==================================================
# ==================================================
# SIDEBAR
# ==================================================

sidebar = ctk.CTkFrame(
    app,
    width=240,
    corner_radius=0,
    fg_color="#151515"
)

sidebar.pack(
    side="left",
    fill="y"
)

sidebar.pack_propagate(False)


# ==================================================
# APP TITLE
# ==================================================

ctk.CTkLabel(
    sidebar,
    text="QUSAI",
    font=ctk.CTkFont(
        size=26,
        weight="bold"
    ),
    text_color="#4EA8DE"
).pack(
    pady=(35, 0)
)


ctk.CTkLabel(
    sidebar,
    text="EXPENSE TRACKER",
    font=ctk.CTkFont(
        size=13,
        weight="bold"
    ),
    text_color="#AAAAAA"
).pack(
    pady=(0, 30)
)


# ==================================================
# SEPARATOR
# ==================================================

ctk.CTkFrame(
    sidebar,
    height=1,
    fg_color="#333333"
).pack(
    fill="x",
    padx=20,
    pady=(0, 20)
)


# ==================================================
# NAVIGATION BUTTONS
# ==================================================

current_screen = {"fn": None}


def create_sidebar_button(
    text,
    command
):

    original_command = command

    def command():
        current_screen["fn"] = original_command
        original_command()

    button = ctk.CTkButton(
        sidebar,
        text=text,
        height=45,
        corner_radius=10,
        fg_color="transparent",
        hover_color="#252525",
        text_color="#DDDDDD",
        anchor="w",
        font=ctk.CTkFont(
            size=14,
            weight="bold"
        ),
        command=command
    )

    button.pack(
        padx=15,
        pady=5,
        fill="x"
    )

    return button


create_sidebar_button(
    "  Dashboard",
    show_dashboard
)

create_sidebar_button(
    "  Transactions",
    show_transactions
)

create_sidebar_button(
    "  Add Expense",
    lambda: show_add_transaction("expense")
)

create_sidebar_button(
    "  Add Income",
    lambda: show_add_transaction("income")
)

create_sidebar_button(
    "  Budgets",
    show_budgets
)

create_sidebar_button(
    "  Statistics",
    show_statistics
)


# ==================================================
# SIDEBAR FOOTER
# ==================================================

ctk.CTkLabel(
    sidebar,
    text="Personal Finance Manager",
    font=ctk.CTkFont(size=11),
    text_color="#666666"
).pack(
    side="bottom",
    pady=20
)

# ==================================================
# MAIN FRAME
# ==================================================

main_frame = ctk.CTkFrame(
    app,
    corner_radius=0
)

main_frame.pack(
    side="right",
    fill="both",
    expand=True
)


# ==================================================
# REFRESH BUTTON (top-right) - reloads data from Supabase
# ==================================================

def refresh_data():

    refresh_button.configure(text="Refreshing...", state="disabled")
    app.update_idletasks()

    try:
        load_cache()
    except Exception as e:
        messagebox.showerror(
            "ExpTrack",
            f"Could not refresh.\n\n{e}"
        )
    else:
        (current_screen["fn"] or show_dashboard)()
    finally:
        refresh_button.configure(text="⟳  Refresh", state="normal")
        refresh_button.lift()


refresh_button = ctk.CTkButton(
    app,
    text="⟳  Refresh",
    width=110,
    height=32,
    corner_radius=8,
    fg_color="#2FA572",
    hover_color="#278B60",
    font=ctk.CTkFont(size=13, weight="bold"),
    command=refresh_data
)

refresh_button.place(relx=1.0, x=-20, y=12, anchor="ne")
refresh_button.lift()

app.bind("<F5>", lambda event: refresh_data())


# ==================================================
# CLOSE APP
# ==================================================

def close_app():
    try:
        conn.close()
    except Exception:
        pass

    app.quit()
    app.destroy()

# ==================================================
# START
# ==================================================

current_screen["fn"] = show_dashboard
show_dashboard()
refresh_button.lift()

app.mainloop()