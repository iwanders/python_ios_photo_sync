#!/bin/bash

source setup.priv.sh
./socketserverREPL/repl_tool.py evaluate "from objc_util import on_main_thread; import console; on_main_thread(console.set_idle_timer_disabled)(True);\n"
