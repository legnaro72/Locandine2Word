import dateparser
from datetime import datetime

d_it = "10 Febbraio 2026"
d_en = "10 February 2026"

p_it = dateparser.parse(d_it, languages=['it'])
p_en = dateparser.parse(d_en, languages=['it'])
p_en_no_lang = dateparser.parse(d_en)

print(f"IT with lang=['it']: {p_it}")
print(f"EN with lang=['it']: {p_en}")
print(f"EN without lang: {p_en_no_lang}")
