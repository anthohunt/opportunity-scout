FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY agent agent
COPY manage.py .
COPY tests tests
# uid/gid 1000 : le dossier de données monté sur /data doit lui appartenir (chown 1000:1000 data)
USER 1000:1000
ENV DATA_DIR=/data
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
