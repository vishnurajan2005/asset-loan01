from apscheduler.schedulers.background import BackgroundScheduler
from datetime import date
from flaskext.mysql import MySQL
import pymysql

mysql = MySQL()

def automation_engine():
    conn = mysql.connect()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, emi_due_date, balance, user_id
        FROM loans
        WHERE status='approved'
    """)

    loans = cursor.fetchall()
    today = date.today()

    for loan in loans:
        loan_id, due_date, balance, _ = loan


        # EMI miss check
        if due_date and today > due_date:
            cursor.execute("""
                UPDATE loans
                SET missed_emis = missed_emis + 1,
                    penalty = penalty + 100
                WHERE id=%s
            """, (loan_id,))

            cursor.execute("""
                INSERT INTO automation_logs(loan_id, action, description)
                VALUES(%s, 'MISSED_EMI', 'EMI missed, penalty added')
            """, (loan_id,))

        # Auto close
        if balance <= 0:
            cursor.execute("""
                UPDATE loans SET status='closed' WHERE id=%s
            """, (loan_id,))

            cursor.execute("""
                INSERT INTO automation_logs(loan_id, action, description)
                VALUES(%s, 'AUTO_CLOSE', 'Loan auto closed')
            """, (loan_id,))

    conn.commit()
    conn.close()


def start_automation(mysql_instance):
    global mysql
    mysql = mysql_instance

    scheduler = BackgroundScheduler()
    scheduler.add_job(automation_engine, 'interval', seconds=30)
    scheduler.start()
