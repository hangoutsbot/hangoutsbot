#!/usr/bin/bash
nohup python3 hangupsbot/hangupsbot.py > stdout.log 2> stderr.log &
echo $! > hangupsbot.pid
