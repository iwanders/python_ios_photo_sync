#!/usr/bin/env bash


source setup.priv.sh
./deploy.sh

./socketserverREPL/repl_tool.py evaluate "import importlib;import phone; importlib.reload(phone); phone.start()"
