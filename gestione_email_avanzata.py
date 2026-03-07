import re
import smtplib
import dns.resolver
import socket
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import os
import threading

socket.setdefaulttimeout(5)

# ------------------ CONTROLLI ------------------

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

def verify_email(email):
    if not check_syntax(email):
        return "Formato non valido"
    if not check_domain(email):
        return "Dominio inesistente"
    return "Valida o non verificabile (SMTP disattivato)"

# ------------------ UI ------------------

root = tk.Tk()
root.withdraw()

file_path = filedialog.askopenfilename(
    title="Seleziona file lista email",
    filetypes=[("File di testo", "*.txt")]
)

if not file_path:
    exit()

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

emails = [e.strip() for e in content.split(",") if e.strip()]

if not emails:
    messagebox.showerror("Errore", "Nessuna email trovata.")
    exit()

scelta = messagebox.askyesnocancel(
    "Modalità operazione",
    "Vuoi VERIFICARE le email?\n\n"
    "Sì = Verifica formato/dominio\n"
    "No = Suddividi in blocchi"
)

if scelta is None:
    exit()

# ============================
# 🔎 MODALITÀ VERIFICA
# ============================
if scelta is True:

    lista_finale = []

    # Finestra log
    log_window = tk.Toplevel()
    log_window.title("Verifica in corso...")
    text_area = tk.Text(log_window, width=80, height=25)
    text_area.pack()

    def process():
        for idx, email in enumerate(emails, 1):
            risultato = verify_email(email)

            text_area.insert(tk.END, f"{idx}/{len(emails)} - {email} -> {risultato}\n")
            text_area.see(tk.END)

            if risultato == "Valida o non verificabile (SMTP disattivato)":
                lista_finale.append(email)
            else:
                risposta = messagebox.askyesno(
                    "Email con problema",
                    f"{email}\n\nProblema: {risultato}\n\nVuoi MANTENERLA?"
                )
                if risposta:
                    lista_finale.append(email)

        save_path = filedialog.asksaveasfilename(
            title="Salva lista verificata",
            defaultextension=".txt",
            filetypes=[("File di testo", "*.txt")]
        )

        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(",".join(lista_finale))

            messagebox.showinfo("Completato",
                                f"Lista salvata.\nEmail finali: {len(lista_finale)}")

        log_window.destroy()

    threading.Thread(target=process).start()
    log_window.mainloop()

# ============================
# 📦 MODALITÀ BLOCCHI
# ============================
else:

    numero_blocco = simpledialog.askinteger(
        "Dimensione blocco",
        "Quante email per blocco?"
    )

    if not numero_blocco or numero_blocco <= 0:
        messagebox.showerror("Errore", "Numero non valido.")
        exit()

    base_dir = filedialog.askdirectory(title="Scegli cartella dove salvare i blocchi")

    if not base_dir:
        exit()

    blocco_num = 1
    for i in range(0, len(emails), numero_blocco):
        blocco = emails[i:i + numero_blocco]
        nome_file = os.path.join(base_dir, f"blocco_{blocco_num}.txt")

        with open(nome_file, "w", encoding="utf-8") as f:
            f.write(",".join(blocco))

        blocco_num += 1

    messagebox.showinfo("Completato",
                        f"Creati {blocco_num - 1} file blocco.")