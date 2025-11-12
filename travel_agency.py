import tkinter as tk
from tkinter import ttk, messagebox
import mysql.connector
from datetime import date, datetime

# -----------------------------
# DB Connection
# -----------------------------
def connect_db():
    try:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="qwerty",  # change if needed
            database="travel_agency_v2"
        )
    except mysql.connector.Error as e:
        messagebox.showerror("DB Error", f"Unable to connect to DB: {e}")
        return None

# -----------------------------
# LOGIN & SIMPLE REGISTER (name,email,password)
# -----------------------------
def register_user_window():
    win = tk.Toplevel()
    win.title("Register New Customer")
    win.geometry("380x300")

    tk.Label(win, text="Register (Name, Email, Password)", font=("Arial", 12, "bold")).pack(pady=8)

    tk.Label(win, text="Full Name").pack(pady=4)
    name_ent = tk.Entry(win, width=40)
    name_ent.pack()

    tk.Label(win, text="Email").pack(pady=4)
    email_ent = tk.Entry(win, width=40)
    email_ent.pack()

    tk.Label(win, text="Password").pack(pady=4)
    pass_ent = tk.Entry(win, width=40, show="*")
    pass_ent.pack()

    def submit_register():
        full_name = name_ent.get().strip()
        email = email_ent.get().strip()
        password = pass_ent.get().strip()

        if not full_name or not email or not password:
            messagebox.showwarning("Missing fields", "Please provide Name, Email and Password.")
            return

        # Split full name into F_name and L_name (best-effort)
        parts = full_name.split()
        f_name = parts[0]
        l_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        # username: use email (keeps it simple)
        username = email
        password_hash = password  # note: stored in DB column password_hash; no hashing here

        db = connect_db()
        if not db:
            return
        cur = db.cursor()
        try:
            # Call RegisterCustomerUser stored procedure.
            # Missing values set to safe defaults: DOB -> NULL, phone -> '', state -> 'N/A', city -> 'N/A', pincode -> ''
            cur.callproc("RegisterCustomerUser", (
                f_name,              # p_F_name
                l_name,              # p_L_name
                email,               # p_email
                None,                # p_DOB (NULL)
                "",                  # p_phone
                "N/A",               # p_state
                "N/A",               # p_city
                "",                  # p_pincode
                username,            # p_username
                password_hash        # p_password_hash
            ))
            db.commit()
            messagebox.showinfo("Registered", "Registration successful. You can now login using Email as username.")
            win.destroy()
        except mysql.connector.IntegrityError as ie:
            db.rollback()
            # probably duplicate username/email
            messagebox.showerror("Registration error", f"Integrity error (maybe email/username already exists): {ie}")
        except Exception as e:
            db.rollback()
            messagebox.showerror("Registration error", f"Failed to register: {e}")
        finally:
            db.close()

    tk.Button(win, text="Register", command=submit_register, bg="#4caf50", fg="white", width=14).pack(pady=12)
    tk.Button(win, text="Cancel", command=win.destroy).pack(pady=6)

def login_user():
    username = entry_username.get().strip()
    password = entry_password.get().strip()

    if not username or not password:
        messagebox.showwarning("Input error", "Please enter username and password.")
        return

    db = connect_db()
    if not db:
        return
    cur = db.cursor(dictionary=True)
    try:
        cur.execute("SELECT * FROM Users WHERE username=%s AND password_hash=%s", (username, password))
        user = cur.fetchone()
    except Exception as e:
        messagebox.showerror("DB Error", f"Login query failed: {e}")
        db.close()
        return

    db.close()
    if not user:
        messagebox.showerror("Login failed", "Invalid username or password.")
        return

    role = user['role']
    if role == 'admin':
        login_window.destroy()
        open_admin_dashboard(user)
    elif role == 'agent':
        login_window.destroy()
        open_agent_dashboard(user)
    elif role == 'customer':
        login_window.destroy()
        open_customer_dashboard(user)
    else:
        messagebox.showerror("Login failed", "Unknown role for this user.")

# -----------------------------
# CUSTOMER DASHBOARD (view/add booking, pay, add review)
# -----------------------------
def open_customer_dashboard(user):
    cust_id = user.get('linked_customer_id')
    username = user.get('username')

    if not cust_id:
        messagebox.showerror("Error", "This user is not linked to a customer record.")
        return

    # price mapping by city (hardcoded)
    destination_prices_map = {
        "Mysuru": 1500.0,
        "Hubli": 700.0,
        "Goa": 3000.0,
        "Bengaluru": 1000.0
    }

    def load_destinations():
        db = connect_db()
        cur = db.cursor()
        cur.execute("SELECT des_id, state, city FROM Destination")
        rows = cur.fetchall()
        db.close()
        dest_map = {}
        for des_id, state, city in rows:
            label = f"{state} - {city} (id:{des_id})"
            dest_map[label] = (des_id, city)
        return dest_map

    def load_agents():
        db = connect_db()
        cur = db.cursor()
        cur.execute("SELECT agent_id, F_name, L_name FROM Agent")
        rows = cur.fetchall()
        db.close()
        ag_map = {}
        for aid, fn, ln in rows:
            label = f"{fn} {ln} (id:{aid})"
            ag_map[label] = aid
        return ag_map

    def load_bookings():
        for i in bookings_tree.get_children():
            bookings_tree.delete(i)
        db = connect_db()
        cur = db.cursor()
        cur.execute("""
            SELECT b.booking_id, b.agent_id, b.book_date, b.travel_date, b.no_of_passengers,
                   b.total_cost, b.status
            FROM Booking b
            WHERE b.customer_id = %s
            ORDER BY b.booking_id DESC
        """, (cust_id,))
        rows = cur.fetchall()
        for booking_id, agent_id, book_date, travel_date, nop, total_cost, status in rows:
            cur.execute("SELECT COALESCE(SUM(amount),0) FROM Payment WHERE booking_id=%s AND status='Completed'", (booking_id,))
            paid = cur.fetchone()[0] or 0
            pay_status = "Completed" if paid >= total_cost else ("Partially Paid" if paid > 0 else "Pending")
            bookings_tree.insert("", tk.END, values=(booking_id, agent_id, book_date, travel_date, nop, f"{total_cost:.2f}", status, pay_status))
        db.close()

    def add_booking_window():
        win = tk.Toplevel()
        win.title("Add Booking")
        win.geometry("440x480")

        tk.Label(win, text="Select Destination:", font=("Arial", 11, "bold")).pack(pady=6)
        dest_cb = ttk.Combobox(win, state="readonly", width=45)
        dest_cb.pack(pady=6)

        tk.Label(win, text="Select Travel Agent:", font=("Arial", 11, "bold")).pack(pady=6)
        agent_cb = ttk.Combobox(win, state="readonly", width=45)
        agent_cb.pack(pady=6)

        tk.Label(win, text="Travel Date (YYYY-MM-DD):").pack(pady=6)
        travel_entry = tk.Entry(win)
        travel_entry.pack()

        tk.Label(win, text="No. of Passengers:").pack(pady=6)
        nop_entry = tk.Entry(win)
        nop_entry.pack()

        price_var = tk.StringVar(value="₹0.00")
        tk.Label(win, text="Total Cost (auto):").pack(pady=6)
        tk.Label(win, textvariable=price_var, font=("Arial", 12, "bold")).pack(pady=4)

        dest_map = load_destinations()
        agent_map = load_agents()
        dest_cb['values'] = list(dest_map.keys())
        agent_cb['values'] = list(agent_map.keys())

        def on_dest_or_nop_change(event=None):
            sel = dest_cb.get()
            nop = nop_entry.get().strip()
            if not sel or not nop.isdigit():
                price_var.set("₹0.00")
                return
            _, city = dest_map.get(sel)
            base_price = destination_prices_map.get(city, 0.0)
            total = base_price * int(nop)
            price_var.set(f"₹{total:.2f}")

        dest_cb.bind("<<ComboboxSelected>>", on_dest_or_nop_change)
        nop_entry.bind("<KeyRelease>", on_dest_or_nop_change)

        def submit_booking():
            sel_dest = dest_cb.get()
            sel_agent = agent_cb.get()
            travel_date_str = travel_entry.get().strip()
            nop = nop_entry.get().strip()

            if not sel_dest or not sel_agent or not travel_date_str or not nop:
                messagebox.showwarning("Missing", "Please fill all fields.")
                return
            try:
                travel_date_obj = datetime.strptime(travel_date_str, "%Y-%m-%d").date()
                nop_i = int(nop)
            except Exception:
                messagebox.showerror("Invalid", "Enter valid date and passenger count.")
                return

            des_id, city = dest_map.get(sel_dest)
            base_price = destination_prices_map.get(city, 0.0)
            total_cost = base_price * nop_i
            agent_id = agent_map.get(sel_agent)
            book_date = date.today().isoformat()
            status = "Pending"

            db = connect_db()
            cur = db.cursor()
            try:
                cur.callproc("AddBooking", (cust_id, agent_id, book_date, status, travel_date_obj.isoformat(), nop_i, total_cost))
                db.commit()
                cur.execute("SELECT LAST_INSERT_ID()")
                last = cur.fetchone()[0]
                cur.execute("INSERT INTO Booking_Destination (booking_id, destination_id) VALUES (%s, %s)", (last, des_id))
                db.commit()
                messagebox.showinfo("Success", f"Booking {last} created successfully.")
                win.destroy()
                load_bookings()
            except Exception as e:
                db.rollback()
                messagebox.showerror("DB Error", f"Failed to add booking: {e}")
            finally:
                db.close()

        tk.Button(win, text="Create Booking", command=submit_booking, bg="#4caf50", fg="white").pack(pady=12)
        tk.Button(win, text="Cancel", command=win.destroy).pack(pady=6)

    def make_payment_window():
        win = tk.Toplevel()
        win.title("Make Payment")
        win.geometry("500x360")

        tk.Label(win, text="Select booking to pay:", font=("Arial", 11)).pack(pady=6)
        pay_cb = ttk.Combobox(win, state="readonly", width=80)
        db = connect_db()
        cur = db.cursor()
        cur.execute("""
            SELECT b.booking_id, b.total_cost,
                   COALESCE((SELECT SUM(amount) FROM Payment p WHERE p.booking_id=b.booking_id AND p.status='Completed'),0)
            FROM Booking b WHERE b.customer_id=%s
        """, (cust_id,))
        pay_rows = cur.fetchall()
        db.close()

        pay_map = {}
        for bid, total, paid in pay_rows:
            remaining = float(total) - float(paid)
            label = f"Booking {bid} | Total ₹{total:.2f} | Paid ₹{paid:.2f} | Remaining ₹{remaining:.2f}"
            pay_map[label] = (bid, remaining)

        pay_cb['values'] = list(pay_map.keys())
        pay_cb.pack(pady=8)

        mode_entry = ttk.Combobox(win, values=["Cash", "Card", "UPI"], state="readonly")
        mode_entry.pack(pady=6)
        mode_entry.set("Cash")

        def submit_payment():
            sel = pay_cb.get()
            if not sel:
                messagebox.showwarning("Select", "Choose a booking.")
                return
            bid, remaining = pay_map[sel]
            if remaining <= 0:
                messagebox.showinfo("Info", "Already fully paid.")
                return

            db = connect_db()
            cur = db.cursor()
            try:
                cur.callproc("AddPayment", (bid, date.today().isoformat(), remaining, mode_entry.get(), "Completed"))
                db.commit()
                messagebox.showinfo("Success", f"Payment ₹{remaining:.2f} done for Booking {bid}.")
                win.destroy()
                load_bookings()
            except Exception as e:
                db.rollback()
                messagebox.showerror("DB Error", f"Payment failed: {e}")
            finally:
                db.close()

        tk.Button(win, text="Pay Remaining (Auto)", command=submit_payment, bg="#1976d2", fg="white").pack(pady=12)
        tk.Button(win, text="Cancel", command=win.destroy).pack(pady=6)

    def add_review_window():
        win = tk.Toplevel()
        win.title("Add Review")
        win.geometry("420x380")

        tk.Label(win, text="Select Destination:", font=("Arial", 11)).pack(pady=6)
        dest_cb = ttk.Combobox(win, state="readonly", width=50)
        dest_map = load_destinations()
        dest_cb['values'] = list(dest_map.keys())
        dest_cb.pack(pady=6)

        tk.Label(win, text="Rating (1-5):").pack(pady=6)
        rating_cb = ttk.Combobox(win, values=[1,2,3,4,5], state="readonly")
        rating_cb.pack(pady=6)

        tk.Label(win, text="Comment:").pack(pady=6)
        comment_ent = tk.Entry(win, width=50)
        comment_ent.pack(pady=6)

        def submit_review():
            sel = dest_cb.get()
            rating = rating_cb.get()
            comment = comment_ent.get().strip()
            if not sel or not rating:
                messagebox.showwarning("Missing", "Select destination and rating.")
                return
            des_id, _ = dest_map.get(sel)
            db = connect_db()
            cur = db.cursor()
            try:
                # agent_id left NULL (as allowed by your AddReview proc)
                cur.callproc("AddReview", (cust_id, des_id, int(rating), comment, None))
                db.commit()
                messagebox.showinfo("Success", "Review added.")
                win.destroy()
            except Exception as e:
                db.rollback()
                messagebox.showerror("DB Error", f"Failed to add review: {e}")
            finally:
                db.close()

        tk.Button(win, text="Submit Review", command=submit_review, bg="#4caf50", fg="white").pack(pady=12)
        tk.Button(win, text="Cancel", command=win.destroy).pack(pady=6)

    # UI setup
    cust_win = tk.Tk()
    cust_win.title(f"Customer Dashboard - {username}")
    cust_win.geometry("1000x620")

    tk.Label(cust_win, text=f"Welcome {username}", font=("Arial", 16, "bold")).pack(pady=8)

    columns = ("Booking ID", "Agent ID", "Book Date", "Travel Date", "Passengers", "Total Cost", "Status", "Pay Status")
    bookings_tree = ttk.Treeview(cust_win, columns=columns, show="headings", height=16)
    for c in columns:
        bookings_tree.heading(c, text=c)
        bookings_tree.column(c, anchor=tk.CENTER, width=120)
    bookings_tree.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    btn_frame = tk.Frame(cust_win)
    btn_frame.pack(pady=8)
    tk.Button(btn_frame, text="View My Bookings", command=load_bookings, bg="#4caf50", fg="white", width=16).grid(row=0, column=0, padx=6)
    tk.Button(btn_frame, text="Add Booking", command=add_booking_window, bg="#ff9800", fg="white", width=16).grid(row=0, column=1, padx=6)
    tk.Button(btn_frame, text="Pay Now", command=make_payment_window, bg="#1976d2", fg="white", width=16).grid(row=0, column=2, padx=6)
    tk.Button(btn_frame, text="Add Review", command=add_review_window, bg="#9c27b0", fg="white", width=16).grid(row=0, column=3, padx=6)
    tk.Button(btn_frame, text="Logout", command=cust_win.destroy, width=12).grid(row=0, column=4, padx=6)

    load_bookings()
    cust_win.mainloop()

# -----------------------------
# AGENT DASHBOARD
# -----------------------------
def open_agent_dashboard(user):
    agent_id = user.get('linked_agent_id')
    username = user.get('username')

    if not agent_id:
        messagebox.showerror("Error", "This user is not linked to an agent record.")
        return

    def load_bookings():
        for i in tree.get_children():
            tree.delete(i)
        db = connect_db()
        cur = db.cursor()
        cur.execute("""
            SELECT b.booking_id, b.customer_id, CONCAT(c.F_name,' ',c.L_name) AS customer_name,
                   b.total_cost, b.status,
                   COALESCE((SELECT SUM(amount) FROM Payment p WHERE p.booking_id=b.booking_id AND p.status='Completed'),0) AS paid
            FROM Booking b
            JOIN Customer c ON b.customer_id=c.customer_id
            WHERE b.agent_id=%s
            ORDER BY b.booking_id DESC
        """, (agent_id,))
        rows = cur.fetchall()
        db.close()
        for bid, cid, cname, total, status, paid in rows:
            pay_status = "Completed" if paid >= total else ("Partially Paid" if paid > 0 else "Pending")
            tree.insert("", tk.END, values=(bid, cid, cname, f"{total:.2f}", status, pay_status))

    def confirm_booking():
        sel = tree.focus()
        if not sel:
            messagebox.showwarning("Select", "Select a booking to confirm.")
            return
        bid = tree.item(sel)["values"][0]
        db = connect_db()
        cur = db.cursor()
        cur.execute("SELECT total_cost, COALESCE(SUM(amount),0) FROM Booking b LEFT JOIN Payment p ON b.booking_id=p.booking_id AND p.status='Completed' WHERE b.booking_id=%s GROUP BY b.booking_id", (bid,))
        row = cur.fetchone()
        if row and row[1] >= row[0]:
            try:
                cur.execute("UPDATE Booking SET status='Confirmed' WHERE booking_id=%s", (bid,))
                db.commit()
                messagebox.showinfo("Confirmed", f"Booking {bid} confirmed.")
                load_bookings()
            except Exception as e:
                db.rollback()
                messagebox.showerror("DB Error", f"Failed to confirm booking: {e}")
        else:
            messagebox.showwarning("Warning", "Booking not fully paid.")
        db.close()

    def view_commission():
        db = connect_db()
        cur = db.cursor()
        try:
            cur.execute("SELECT GetAgentCommission(%s)", (agent_id,))
            comm = cur.fetchone()[0] or 0
            messagebox.showinfo("Commission", f"Total Commission: ₹{float(comm):.2f}")
        except Exception as e:
            messagebox.showerror("DB Error", f"Failed to get commission: {e}")
        finally:
            db.close()

    win = tk.Tk()
    win.title(f"Agent Dashboard - {username}")
    win.geometry("980x540")

    tk.Label(win, text=f"Welcome Agent {username}", font=("Arial", 16, "bold")).pack(pady=8)

    columns = ("Booking ID", "Customer ID", "Customer Name", "Total", "Status", "Pay Status")
    tree = ttk.Treeview(win, columns=columns, show="headings", height=16)
    for c in columns:
        tree.heading(c, text=c)
        tree.column(c, anchor=tk.CENTER, width=140)
    tree.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    btn_frame = tk.Frame(win)
    btn_frame.pack(pady=8)
    tk.Button(btn_frame, text="Refresh", command=load_bookings, bg="#4caf50", fg="white", width=14).grid(row=0, column=0, padx=8)
    tk.Button(btn_frame, text="Confirm (if Paid)", command=confirm_booking, bg="#ff9800", fg="white", width=18).grid(row=0, column=1, padx=8)
    tk.Button(btn_frame, text="My Commission", command=view_commission, bg="#2196f3", fg="white", width=16).grid(row=0, column=2, padx=8)
    tk.Button(btn_frame, text="Logout", command=win.destroy, width=12).grid(row=0, column=3, padx=8)

    load_bookings()
    win.mainloop()

# -----------------------------
# ADMIN DASHBOARD
# -----------------------------
def open_admin_dashboard(user):
    def show_customers():
        for i in tree.get_children():
            tree.delete(i)
        db = connect_db()
        cur = db.cursor()
        cur.execute("SELECT customer_id, F_name, L_name, email, phone, city FROM Customer")
        rows = cur.fetchall()
        db.close()
        for r in rows:
            tree.insert("", tk.END, values=r)

    def show_agents():
        for i in tree.get_children():
            tree.delete(i)
        db = connect_db()
        cur = db.cursor()
        cur.execute("SELECT agent_id, F_name, L_name, email, contact_no, commission_percent, salary FROM Agent")
        rows = cur.fetchall()
        db.close()
        for r in rows:
            tree.insert("", tk.END, values=r)

    def show_reviews():
        for i in tree.get_children():
            tree.delete(i)
        db = connect_db()
        cur = db.cursor()
        cur.execute("""
            SELECT r.review_id, CONCAT(c.F_name,' ',c.L_name) AS customer, d.state, d.city,
                   r.rating, r.comment, r.agent_id
            FROM Review r
            LEFT JOIN Customer c ON r.customer_id = c.customer_id
            LEFT JOIN Destination d ON r.destination_id = d.des_id
            ORDER BY r.review_id DESC
        """)
        rows = cur.fetchall()
        db.close()
        for r in rows:
            tree.insert("", tk.END, values=r)

    def destination_stats_window():
        win = tk.Toplevel()
        win.title("Destination Stats")
        win.geometry("760x480")

        cols = ("Destination", "FN BookingCount", "BD BookingCount", "Total Payments (Completed)")
        t = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            t.heading(c, text=c)
            t.column(c, width=180, anchor=tk.CENTER)
        t.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        db = connect_db()
        cur = db.cursor()
        cur.execute("SELECT des_id, state, city FROM Destination")
        dests = cur.fetchall()

        for des_id, state, city in dests:
            label = f"{state} - {city} (id:{des_id})"
            # function call
            try:
                cur.execute("SELECT GetBookingCountByDestination(%s)", (des_id,))
                fn_count = cur.fetchone()[0] or 0
            except Exception:
                fn_count = "ERR"
            cur.execute("SELECT COUNT(*) FROM Booking_Destination WHERE destination_id=%s", (des_id,))
            bd_count = cur.fetchone()[0] or 0
            cur.execute("""
                SELECT COALESCE(SUM(p.amount),0)
                FROM Payment p
                JOIN Booking_Destination bd ON p.booking_id = bd.booking_id
                WHERE bd.destination_id=%s AND p.status='Completed'
            """, (des_id,))
            total_pay = cur.fetchone()[0] or 0
            t.insert("", tk.END, values=(label, fn_count, bd_count, f"₹{float(total_pay):.2f}"))

        db.close()

    win = tk.Tk()
    win.title("Admin Dashboard")
    win.geometry("1200x640")

    tk.Label(win, text="Admin Dashboard", font=("Arial", 16, "bold")).pack(pady=8)

    columns = ("Col1", "Col2", "Col3", "Col4", "Col5", "Col6", "Col7")
    tree = ttk.Treeview(win, columns=columns, show="headings", height=20)
    for c in columns:
        tree.heading(c, text=c)
        tree.column(c, anchor=tk.CENTER, width=150)
    tree.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    btn_frame = tk.Frame(win)
    btn_frame.pack(pady=6)
    tk.Button(btn_frame, text="View Customers", command=show_customers, bg="#4caf50", fg="white", width=18).grid(row=0, column=0, padx=6)
    tk.Button(btn_frame, text="View Agents", command=show_agents, bg="#2196f3", fg="white", width=18).grid(row=0, column=1, padx=6)
    tk.Button(btn_frame, text="View Reviews", command=show_reviews, bg="#9c27b0", fg="white", width=18).grid(row=0, column=2, padx=6)
    tk.Button(btn_frame, text="Destination Stats", command=destination_stats_window, bg="#ff9800", fg="white", width=18).grid(row=0, column=3, padx=6)
    tk.Button(btn_frame, text="Logout", command=win.destroy, width=12).grid(row=0, column=4, padx=6)

    win.mainloop()

# -----------------------------
# MAIN LOGIN WINDOW
# -----------------------------
login_window = tk.Tk()
login_window.title("Travel Agency v2 - Login")
login_window.geometry("460x320")

tk.Label(login_window, text="Travel Agency v2", font=("Arial", 16, "bold")).pack(pady=10)
tk.Label(login_window, text="Username (email)").pack(pady=6)
entry_username = tk.Entry(login_window)
entry_username.pack(pady=4)
tk.Label(login_window, text="Password").pack(pady=6)
entry_password = tk.Entry(login_window, show="*")
entry_password.pack(pady=4)

btn_frame = tk.Frame(login_window)
btn_frame.pack(pady=10)
tk.Button(btn_frame, text="Login", command=login_user, bg="#1976d2", fg="white", width=12).grid(row=0, column=0, padx=6)
tk.Button(btn_frame, text="Register", command=register_user_window, bg="#4caf50", fg="white", width=12).grid(row=0, column=1, padx=6)
tk.Button(btn_frame, text="Exit", command=login_window.destroy, width=12).grid(row=0, column=2, padx=6)

login_window.mainloop()
