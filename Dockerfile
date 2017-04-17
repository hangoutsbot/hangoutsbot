FROM python:3.4.6-alpine

# Install Git with PIP
RUN apk update && apk upgrade
RUN apk add git

# Add dumb-init for safely handling signals
ADD https://github.com/Yelp/dumb-init/releases/download/v1.1.1/dumb-init_1.1.1_amd64 /usr/local/bin/dumb-init
# Make dumb-init executable.
RUN chmod +x /usr/local/bin/dumb-init

# Creates a non-root-user.
RUN addgroup -S hbot && adduser -S -g hbot hbot
# Set the current working directory and create it if it doesn't exists
WORKDIR /home/hbot/hangoutsbot

# Add all files to the working dir
ADD . . 

# Install dependencies as the root.
RUN pip3 install -r requirements.txt

# Uncomment to install latest version of hangups
#RUN apk update && apk upgrade && apk add gcc make
#RUN git clone https://github.com/tdryer/hangups.git /hangups
#RUN cd /hangups && python3 setup.py install

# Sets the HOME environment variable.
ENV HOME=/home/hbot
# Make everything in the home directory belong to amonra user.
RUN chown hbot:hbot -R $HOME/*
# Execute everything below this as the amonra user for security reasons.
USER hbot

# Start the Docker containers with the hangoutsbot.py as the entrypoint
ENTRYPOINT ["dumb-init", "python3", "/home/hbot/hangoutsbot/hangupsbot/hangupsbot.py"]
