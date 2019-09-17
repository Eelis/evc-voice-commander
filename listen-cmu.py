#!/usr/bin/env python3

# prerequisites:
# - sudo apt install swig
# - pip3 install pocketsphinx

import pocketsphinx
import sys

for phrase in pocketsphinx.LiveSpeech():
    print(phrase)
    sys.stdout.flush()
