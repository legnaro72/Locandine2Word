from github import Github
import sys
import streamlit as st

# Prova a prendere il token da st.secrets (per compatibilità locale/cloud)
token = st.secrets.get("GITHUB_TOKEN", None)

if not token:
    print("ERRORE: GITHUB_TOKEN non trovato nei Secrets.")
    sys.exit(1)

try:
    g = Github(token)
    user = g.get_user()
    print(f"Authenticated as: {user.login}")
    
    print("Repositories:")
    for repo in user.get_repos():
        print(repo.full_name)
        
except Exception as e:
    print(f"Error: {e}")
