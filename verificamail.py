import re
import smtplib
import dns.resolver
import socket

# Timeout breve per non bloccare tutto
socket.setdefaulttimeout(10)

def check_syntax(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def check_domain(email):
    domain = email.split('@')[1]
    try:
        records = dns.resolver.resolve(domain, 'MX')
        return records
    except:
        return None

def check_smtp(email):
    domain = email.split('@')[1]
    try:
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(mx_records[0].exchange)

        server = smtplib.SMTP()
        server.connect(mx_record)
        server.helo("example.com")
        server.mail("test@example.com")
        code, message = server.rcpt(email)
        server.quit()

        if code == 250:
            return True
        else:
            return False
    except:
        return False

def verify_email(email):
    print(f"\nVerifica: {email}")

    if not check_syntax(email):
        print("❌ Formato non valido")
        return

    if not check_domain(email):
        print("❌ Dominio inesistente")
        return

    if check_smtp(email):
        print("✅ Email valida")
    else:
        print("⚠️ Email NON verificabile o inesistente")

# ----------- USO -----------

emails = [
    "federicafumagalli2000@gmail.com",
    "indirizzo_sbagliato@gmail",
]

for e in emails:
    verify_email(e)