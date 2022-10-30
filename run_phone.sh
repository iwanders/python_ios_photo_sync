#!/bin/bash

./deploy.sh

./socketserverREPL/repl_tool.py evaluate "import importlib;import phone; importlib.reload(phone); phone.start()"
