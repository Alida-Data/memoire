FROM python:3.10-slim

WORKDIR /app

# Copie des fichiers requis
COPY requirements.txt .

# Installation des dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code applicatif
COPY . .

# Exposer le port de Streamlit
EXPOSE 8501

# Lancement de l'application
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]