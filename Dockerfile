FROM python:3.4.2

WORKDIR /app

COPY . /app

RUN pip install -r requirements.txt

ENTRYPOINT ["python", "/app/hangupsbot/hangupsbot.py"]