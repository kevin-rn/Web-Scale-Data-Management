FROM python:3.10-slim

WORKDIR /home/flask-app

COPY ./requirements.txt .

RUN  python -m pip install --upgrade pip &&\
    pip install -r requirements.txt

COPY . .

EXPOSE 5000