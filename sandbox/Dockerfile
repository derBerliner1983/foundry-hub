FROM python:3.12-slim

WORKDIR /app

# Build-Werkzeuge: Compiler, Node/npm, Java/Gradle-Basis, Zip, Git.
# (Für echte APK-Builds zusätzlich Android-SDK ergänzen; siehe README.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential gcc g++ make git zip unzip curl \
        nodejs npm default-jdk \
    && rm -rf /var/lib/apt/lists/*

COPY sandbox/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Häufige Build-Tools für Artefakte (Python-EXE, Cross-Compile)
RUN pip install --no-cache-dir pyinstaller

COPY sandbox/sandbox_api.py /app/sandbox_api.py

ENV PYTHONUNBUFFERED=1 WORKSPACE_DIR=/data/workspace
EXPOSE 8800
CMD ["uvicorn", "sandbox_api:app", "--host", "0.0.0.0", "--port", "8800"]
