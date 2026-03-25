from flask import Flask, render_template, request, redirect, session, flash

import pymysql
pymysql.install_as_MySQLdb()

from flaskext.mysql import MySQL

from automation import start_automation   # automation engine



LOGIN_URL = '/login'

app = Flask(__name__)
app.secret_key = "asset_secret_key"

# ---------------- EMI ENGINE ----------------

def calculate_emi(principal, annual_rate, tenure_months):
    rate = annual_rate / (12 * 100)
    emi = (principal * rate * ((1 + rate) ** tenure_months)) / (((1 + rate) ** tenure_months) - 1)
    return round(emi, 2)



# ---------------- DATABASE CONFIG ----------------

mysql = MySQL()
app.config['MYSQL_DATABASE_USER'] = 'root'
app.config['MYSQL_DATABASE_PASSWORD'] = 'GSvr_2005'
app.config['MYSQL_DATABASE_DB'] = 'asset_loan_db'
app.config['MYSQL_DATABASE_HOST'] = 'localhost'
mysql.init_app(app)

# ---------------- AUTH ----------------

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']

    conn = mysql.connect()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, role FROM users WHERE email=%s AND password=%s",
        (email, password)
    )
    user = cursor.fetchone()

    if user:
        session['user_id'] = user[0]
        session['role'] = user[1]

        if user[1] == 'admin':
            return redirect('/admin')
        else:
            return redirect('/customer')
    else:
        return "Invalid Login"



# ================= ADMIN ROUTES =================

@app.route('/admin')
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'role' in session and session['role'] == 'admin':
        return render_template('admin.html')
    return redirect('/login')



@app.route('/admin/add_asset', methods=['GET', 'POST'])
def admin_add_asset():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    if request.method == 'POST':
        asset_type = request.form['asset_type']
        asset_name = request.form['asset_name']
        value = request.form['value']

        conn = mysql.connect()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO assets (asset_type, asset_name, asset_value, status)
            VALUES (%s, %s, %s, 'available')
        """, (asset_type, asset_name, value))

        conn.commit()
        conn.close()

        flash("Asset added successfully", "success")
        return redirect('/admin/view_assets')

    return render_template('add_asset.html')


       


@app.route('/admin/view_assets')
def admin_view_assets():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = mysql.connect()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT * FROM assets")
    assets = cursor.fetchall()
    conn.close()

    return render_template('view_assets.html', assets=assets)


@app.route('/admin/approve_loans')
def admin_approve_loans():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = mysql.connect()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("""
    SELECT 
        l.id,
        u.email AS user_name,
        a.asset_name AS asset_name,
        l.loan_amount,
        l.tenure,
        l.status
    FROM loans l
    JOIN users u ON l.user_id = u.id
    JOIN assets a ON l.asset_id = a.id
    WHERE l.status = 'pending'
""")

    loans = cursor.fetchall()
    conn.close()

    return render_template('approve_loans.html', loans=loans)
@app.route('/admin/approve_loan/<int:loan_id>')
def approve_loan(loan_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = mysql.connect()
    cursor = conn.cursor()

    # Get loan details
    cursor.execute("SELECT loan_amount, tenure FROM loans WHERE id=%s", (loan_id,))
    loan = cursor.fetchone()

    if not loan:
        conn.close()
        flash("Loan not found", "error")
        return redirect('/admin/approve_loans')

    P = float(loan[0])   # principal
    N = int(loan[1])     # tenure (months)
    annual_rate = 10     # fixed interest %

    # EMI calculation
    rate = annual_rate / (12 * 100)
    emi = (P * rate * ((1 + rate) ** N)) / (((1 + rate) ** N) - 1)
    emi = round(emi, 2)

    # Update loan
    cursor.execute("""
        UPDATE loans
        SET status='approved',
            emi=%s,
            balance=%s,
            emi_due_date = DATE_ADD(CURDATE(), INTERVAL 1 MONTH)
        WHERE id=%s
    """, (emi, P, loan_id))

    conn.commit()
    conn.close()

    flash("Loan approved successfully", "success")
    return redirect('/admin/approve_loans')

@app.route('/admin/reject_loan/<int:loan_id>', methods=['POST'])
def reject_loan(loan_id):
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = mysql.connect()
    cursor = conn.cursor()

    # Unlock asset
    cursor.execute("""
        UPDATE assets 
        SET status='available'
        WHERE id = (SELECT asset_id FROM loans WHERE id=%s)
    """, (loan_id,))

    # Reject loan
    cursor.execute("""
        UPDATE loans
        SET status='rejected'
        WHERE id=%s
    """, (loan_id,))

    conn.commit()
    conn.close()

    flash("Loan rejected successfully", "error")
    return redirect('/admin/approve_loans')


@app.route('/admin/transactions')
def admin_transactions():
    if 'role' not in session or session['role'] != 'admin':
        return redirect('/login')

    conn = mysql.connect()
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("""
        SELECT 
            t.id,
            t.loan_id,
            u.name AS user_name,
            t.amount,
            t.action,
            t.txn_type,
            t.action_date
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
        ORDER BY t.action_date DESC
    """)

    transactions = cursor.fetchall()
    conn.close()

    return render_template('admin_transactions.html', transactions=transactions)





# ---------------- CUSTOMER ----------------

@app.route('/customer')
def customer():
    if 'role' in session and session['role'] == 'customer':
        return render_template('customer.html')
    return redirect('/')

# ---------------- APPLY LOAN ----------------

@app.route('/apply_loan_page')
def apply_loan_page():
    if 'role' in session and session['role'] == 'customer':
        conn = mysql.connect()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM assets WHERE status='available'")
        assets = cursor.fetchall()

        return render_template('apply_loan.html', assets=assets)

    return redirect('/')

@app.route('/apply_loan', methods=['POST'])
def apply_loan():
    if 'role' in session and session['role'] == 'customer':

        user_id = session['user_id']
        asset_id = request.form['asset_id']
        loan_amount = float(request.form['loan_amount'])
        tenure = int(request.form['tenure'])

        conn = mysql.connect()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO loans(
                user_id, asset_id, loan_amount, interest_rate,
                tenure, status, balance, emi_due_date, missed_emis, penalty, default_flag
            )
            VALUES(%s,%s,%s,10,%s,'pending',%s, CURDATE(), 0, 0, 0)
        """, (user_id, asset_id, loan_amount, tenure, loan_amount))

        cursor.execute("UPDATE assets SET status='locked' WHERE id=%s", (asset_id,))
        conn.commit()
        conn.close()

        return redirect('/customer')

    return redirect('/')

# ---------------- MY LOANS ----------------

@app.route('/my_loans')
def my_loans():
    user_id = session.get('user_id')

    conn = mysql.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT l.id, a.asset_name, l.loan_amount, l.tenure, l.status, l.balance
        FROM loans l
        JOIN assets a ON l.asset_id = a.id
        WHERE l.user_id = %s
    """, (user_id,))

    rows = cursor.fetchall()
    loans = []

    for r in rows:
        loans.append({
            "id": r[0],
            "asset": r[1],
            "amount": float(r[2]),
            "tenure": r[3],
            "status": r[4],
            "balance": float(r[5])
        })

    return render_template('my_loans.html', loans=loans)

# ---------------- REPAYMENTS ----------------

@app.route('/repayments')
def repayments():
    user_id = session.get('user_id')

    conn = mysql.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT l.id, a.asset_name, l.loan_amount, l.tenure, l.balance, l.status, l.emi
        FROM loans l
        JOIN assets a ON l.asset_id = a.id
        WHERE l.user_id = %s AND l.status = 'approved'
    """, (user_id,))

    rows = cursor.fetchall()
    repayments = []

    for r in rows:
        repayments.append({
            "loan_id": r[0],
            "asset_name": r[1],
            "loan_amount": r[2],
            "tenure": r[3],
            "balance": r[4],
            "status": r[5],
            "emi": r[6]
        })

    return render_template("repayment.html", loans=repayments)

# ---------------- PAY EMI ----------------

@app.route('/pay_emi/<int:loan_id>', methods=['GET'])
def pay_emi(loan_id):
    user_id = session.get('user_id')

    conn = mysql.connect()
    cursor = conn.cursor()

    # Get loan info
    cursor.execute("""
        SELECT emi, balance, emi_paid_count, tenure
        FROM loans
        WHERE id=%s AND user_id=%s AND status='approved'
    """, (loan_id, user_id))

    row = cursor.fetchone()

    if not row:
        conn.close()
        flash("Loan not found or not approved", "error")
        return redirect('/repayments')

    emi, balance, paid_count, _ = row

    # Safety check
    if emi is None or emi <= 0:
        conn.close()
        flash("EMI not generated for this loan", "error")
        return redirect('/repayments')

    new_balance = float(balance) - float(emi)
    paid_count = int(paid_count) + 1

    status = 'approved'
    if new_balance <= 0:
        new_balance = 0
        status = 'closed'

    # Update loan
    cursor.execute("""
        UPDATE loans
        SET balance=%s,
            emi_paid_count=%s,
            status=%s,
            emi_due_date = DATE_ADD(emi_due_date, INTERVAL 1 MONTH)
        WHERE id=%s
    """, (new_balance, paid_count, status, loan_id))

    # Log transaction
    cursor.execute("""
        INSERT INTO transactions(loan_id, user_id, amount, txn_type)
        VALUES(%s,%s,%s,'EMI')
    """, (loan_id, user_id, emi))

    conn.commit()
    conn.close()

    flash("✅ EMI paid successfully", "success")
    return redirect('/repayments')





# ---------------- LOGOUT ----------------

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------------- RUN ----------------

if __name__ == '__main__':
    start_automation(mysql)   # background engine
    app.run(debug=True)







    




