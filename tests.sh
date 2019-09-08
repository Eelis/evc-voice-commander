#!/bin/bash

set -e

if [ "$#" -ne 1 ]; then
    expected=/tmp/evc-tests-expected-output
    actual=/tmp/evc-tests-actual-output
    grep -oP "^ *(#[>]|t) \K.*" tests.sh > $expected
    ./tests.sh output > $actual
    diff -u $expected $actual
    exit
fi


function t() {
    echo $*
    ./execute --configdir=example_config --prompt=False --dryrun --volume=0 --color=False $*
}

########################### TEST CASES: ###########################

# simple printing
t computer print hello
    #> hello

# repetition
t computer 3 times print hello
    #> hello
    #> hello
    #> hello

# 'return' builtin
t computer builtin return 3
    #> 3

# 'evaluate'
t computer builtin return evaluate builtin return 5
    #> 5

# arithmetic
t calculate 4 plus 2
    #> 6

# nested arithmetic with 'evaluate'
t calculate 2 plus evaluate 3 times 4
    #> 14

# run
t computer calendar
    #> run urxvt -e zsh -c 'cal; sleep 1000'
