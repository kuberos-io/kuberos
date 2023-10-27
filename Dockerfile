FROM python:3.9-bullseye

ADD requirements.txt /tmp/requirements.txt

RUN pip --no-cache-dir install -r /tmp/requirements.txt

ADD kuberos /kuberos
WORKDIR /kuberos

EXPOSE 8000

CMD ["gunicorn", "--bind", ":8000", "--workers", "4", "settings.wsgi"]
