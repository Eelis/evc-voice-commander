# EVC Voice Commander

## 1. Introduction

EVC is a tool for controlling a computer by speaking commands to it.

Features:

- controls the desktop and applications by simulating key presses
- suitable for everything except fast text entry (dictation)
- should work with any automatic speech recognition (ASR) system that can print
  transcribed utterances to stdout as text (scripts for kaldi and cmu pocketsphinx
  are provided)
- simple but powerful command language
- clean YAML-based config for command definitions, see [example config](example_config/modes.yaml)
- command line prompt for visual and audio feedback (TODO: screenshot)
- command groups for applications auto-enabled based on process name or window title


## 2. Usage:

    mkdir ~/.evc-voice-controller
    cp example_config/* ~/.evc-voice-controller/
    ./evc
