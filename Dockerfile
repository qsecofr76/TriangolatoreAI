# Usa un'immagine ufficiale di Python leggera
FROM python:3.10-slim

# Impedisce a Python di scrivere file .pyc su disco e lo forza a non bufferizzare lo stdout/stderr
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Imposta la directory di lavoro all'interno del container
WORKDIR /app

# Copia prima il file requirements.txt per sfruttare la cache di sistema
COPY requirements.txt .

# Installa le dipendenze
RUN pip install --no-cache-dir -r requirements.txt

# Copia tutto il resto del progetto (escluso ciò che è nel .dockerignore)
COPY . .

# Comando di avvio. 
# Google Cloud Run passa in automatico la variabile di sistema $PORT (di solito 8080).
# Usiamo gunicorn per avviare l'app in ascolto su quella porta.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
