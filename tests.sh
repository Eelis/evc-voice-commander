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
    #> mode computer, print hello, mode control-structures, mode computer, print hello, mode control-structures, mode computer, print hello, mode control-structures, nop
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

# complex custom types (<target>)
t focus change next work space
    #> press wmkey+d, press wmkey+pagedown, press wmkey+a

# current mode overrides auto-enabled modes
t focus,vim,term left
    #> press wmkey+left

# diagnostic for bad command
t computer focus lol
    #> error: expected command
    #> mode mode-map, mode focus

# equally long but faulty match in non-current mode:
t vim-find,vim go
    #> press enter, mode vim

# routing through mode map
t computer edit insert text bla escape
    #> mode mode-map, mode vim, press insert, mode vim-insert, text bla, press escape, mode vim
