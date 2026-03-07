import re
import smtplib
import dns.resolver
import socket
import tkinter as tk
from tkinter import filedialog, messagebox

socket.setdefaulttimeout(10)

# ---------- CONTROLLI ----------

def check_syntax(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

def check_domain(email):
    try:
        domain = email.split('@')[1]
        dns.resolver.resolve(domain, 'MX')
        return True
    except:
        return False

def check_smtp(email):
    try:
        domain = email.split('@')[1]
        mx_records = dns.resolver.resolve(domain, 'MX')
        mx_record = str(mx_records[0].exchange)

        server = smtplib.SMTP(timeout=10)
        server.connect(mx_record)
        server.helo("example.com")
        server.mail("test@example.com")
        code, message = server.rcpt(email)
        server.quit()

        return code == 250
    except:
        return False

def verify_email(email):
    if not check_syntax(email):
        return "Formato non valido"
    if not check_domain(email):
        return "Dominio inesistente"
    if not check_smtp(email):
        return "Casella non verificabile o inesistente"
    return "Valida"

# ---------- SELEZIONE FILE ----------

root = tk.Tk()
root.withdraw()  # Nasconde finestra principale

file_path = filedialog.askopenfilename(
    title="Seleziona il file con la lista email",
    filetypes=[("File di testo", "*.txt")]
)

if not file_path:
    print("Nessun file selezionato.")
    exit()

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

emails = [e.strip() for e in content.split(",") if e.strip()]
lista_finale = []

print(f"\nTotale email trovate: {len(emails)}")

# ---------- VERIFICA INTERATTIVA ----------

for email in emails:
    print(f"\nVerifica: {email}")
    risultato = verify_email(email)
    print("Risultato:", risultato)

    if risultato == "Valida":
        lista_finale.append(email)
    else:
        risposta = messagebox.askyesno(
            "Email con problema",
            f"{email}\n\nProblema: {risultato}\n\nVuoi MANTENERLA nella lista?"
        )
        if risposta:
            lista_finale.append(email)

# ---------- SALVATAGGIO ----------

output_path = filedialog.asksaveasfilename(
    title="Salva la nuova lista",
    defaultextension=".txt",
    filetypes=[("File di testo", "*.txt")]
)

if output_path:
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(",".join(lista_finale))

    messagebox.showinfo("Completato", f"Nuova lista salvata con {len(lista_finale)} email.")
else:
    print("Salvataggio annullato.")