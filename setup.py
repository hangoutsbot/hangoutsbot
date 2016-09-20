import os
from subprocess import call

import sys

path_virtualenv = input("Enter the path for the virtualenv [bot_env]")

if path_virtualenv == "":
    path_virtualenv = "bot_env"

if os.path.exists(path_virtualenv):
    while((use_existing = input("Directory already exists, use this anyway? [J/n]")) not in ["", "y", "n", "q"]):
        if not use_existing.lower() == "y" and not use_existing == "":
            sys.exit()
else:
    os.makedirs(path_virtualenv)

