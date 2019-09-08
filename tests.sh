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

# arithmetic
t computer builtin 4 plus 2
    #> 6

# more arithmetic
t computer builtin 5 plus evaluate builtin 2 times 4
    #> 13

# 'evaluate'
t computer builtin return evaluate builtin return 5
    #> 5
