# EVC Voice Commander

EVC is a tool for controlling a computer by speaking commands to it.

## 1. Features

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

## 2. Installation

Installing prerequisites on Ubuntu:

    sudo apt install docker.io python3-click python3-termcolor python3-pygame libasound2-dev python3-pyaudio

Build the Kaldi ASR docker image (this can take half an hour, as it involves building Kaldi from source):

    ./build-kaldi.sh

## 3. Configuration

    mkdir ~/.evc-voice-commander
    cp example_config/* ~/.evc-voice-commander/
    vim ~/.evc-voice-commander/modes.yaml

## 4. Usage:

    ./evc-voice-commander
