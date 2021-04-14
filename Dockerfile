FROM python:latest
LABEL description="Google Hangouts Bot" \
    maintainer="http://github.com/hangoutsbot/hangoutsbot"
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY ["docker-entrypoint.sh", "hangupsbot/", "./"]
RUN mkdir /data && \    
    mkdir -p /root/.local/share && \
    ln -s /data /root/.local/share/hangupsbot && \
    mkdir /plugins && \
    ln -s /plugins /app/plugins/dockerplugins

VOLUME /data
VOLUME /plugins
ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "hangupsbot.py"]
ARG PORTS="9001 9002 9003"
EXPOSE $PORTS
