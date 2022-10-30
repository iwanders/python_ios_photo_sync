# Python iOS photo sync

Python scripts to sync an (non jailbroken) iPhone's photos to a linux (or windows / mac) computer
without iTunes or iCloud. This runs a server on the phone using [Pythonista][pythonista], then the
computer communicates to this server to obtain the photos.

This is a rewrite from my original version, as such, it is alpha quality. Doesn't support bulk
deletion yet either.

> **Warning**
> Only run any of this on a network you completely trust. There is no authentication or encryption.

## Usage

Copy [`phone.py`](phone.py) to your phone. Run that in Pythonista 3.

Then on the PC it's easiest set the following environment variable to the hostname of your phone;
```
export REPL_HOST=<iphone_hostname>.local
```

After that one can run:
```
./sync.py sync --dir "/tmp/my_photo_storage/"
```

Syncing looks like:
```
  449 /   478:        IMG_0397.HEIC 2022-10-29 23:51:50 (  2030072 bytes)
  450 /   478:        IMG_0398.HEIC 2022-10-29 23:52:00 (  1851551 bytes)
  451 /   478:         IMG_0399.PNG 2022-10-30 15:30:45 (   648208 bytes)
```

Default file structure is:
```
/tmp/my_photo_storage/$ tree
.
├── 2017-02
│   ├── 022D9E6D-D313-428A-B41D-2D3961BA2C39.JPG
│   ├── 11D78EF4-E98D-4B64-90E4-697C854148D9.JPG
│   └── metadata
│       ├── 022D9E6D-D313-428A-B41D-2D3961BA2C39.json
│       └── 11D78EF4-E98D-4B64-90E4-697C854148D9.json
```

This can be modified with commandline arguments.

## Development
Use the `socketserverREPL` functionality, start that on the phone and use
[`run_phone.sh`](run_phone.sh). After closing the connection from the REPL, be sure to load the
`http://<iphone_hostname>.local:1338` a few times to ensure the connection is refused before running
this script again to deploy and run the latest.

Easiest way to bootstrap this is to run `python3 -m http.server` on your PC, open the
`socketserverREPL.py` script in the browser on your phone, copy all the text, then paste this into
a new script in Pythonista, then run that.


[pythonista]: http://omz-software.com/pythonista/


