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
    python3 execute.py --configdir=example_config --prompt=False --printactions --dryrun --volume=0 --color=False $*
}

########################### TEST CASES: ###########################

# repetition
t computer 3 times print hello world
    #> print hello world, print hello world, print hello world
    #> hello world
    #> hello world
    #> hello world

# arithmetic
t arith-demo fibonacci 7
    #> 13

# complex custom types (<target>)
t focus change next work space
    #> press wmkey+d, press wmkey+pagedown, press wmkey+a

# current mode overrides auto-enabled modes
t focus,vim,term left
    #> press wmkey+left

# diagnostic for bad command
t computer focus lol
    #> error: expected command

# equally long but faulty match in non-current mode:
t vim-find,vim go
    #> press enter

# routing through mode map
t computer edit insert text bla escape
    #> press insert, text bla, press escape

# conditionals
t calculate maximum of 2 and 9
    #> 9
t calculate maximum of 9 and 2
    #> 9

# quoting
t computer say good morning
    #> execute zsh -c "echo \"(SayText \\\"good morning\\\")\" | festival"

t computer 3 times say hello
    #> execute zsh -c "echo \"(SayText \\\"hello\\\")\" | festival", execute zsh -c "echo \"(SayText \\\"hello\\\")\" | festival", execute zsh -c "echo \"(SayText \\\"hello\\\")\" | festival"
