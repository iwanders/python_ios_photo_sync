#!/bin/bash

./socketserverREPL/repl_tool.py upload phone.py


./socketserverREPL/repl_tool.py evaluate "import importlib;import phone; importlib.reload(phone); phone.test_image_data()"

