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
t computer arith-demo fibonacci 7
    #> 13

# complex custom types (<target>)
t focus change next work space
    #> press wmkey+d, press wmkey+pagedown, press wmkey+a

# current mode overrides auto-enabled modes
t --modes=focus,vim,term left
    #> press wmkey+left

# diagnostic for bad command
t computer focus lol
    #> error: no such command

# equally long but faulty match in non-current mode:
t --modes=vim-find,vim go
    #> press enter

# routing through mode map
t computer edit insert text bla
    #> press insert, text bla

# conditionals
t computer calculate maximum of 2 and 9
    #> 9
t computer calculate maximum of 9 and 2
    #> 9

# quoting
t computer say good morning
    #> execute zsh -c "echo \"(SayText \\\"good morning\\\")\" | festival"

t computer 3 times say hello
    #> execute zsh -c "echo \"(SayText \\\"hello\\\")\" | festival", execute zsh -c "echo \"(SayText \\\"hello\\\")\" | festival", execute zsh -c "echo \"(SayText \\\"hello\\\")\" | festival"

t computer vim 3 times delete last word
    #> press b, text dw, press b, text dw, press b, text dw

t --modes=zsh computer show files
    #> text ls -l, press enter

t computer show files
    #> run urxvt -e zsh --interactive -c "unset LESS; ls -l | less -r"

t computer 2 times focus right
    #> press wmkey+right, press wmkey+right

t --modes=vim computer control 2 times save
    #> press ctrl+s, press ctrl+s

t focus change 3 times right
    #> press wmkey+d, press wmkey+right, press wmkey+right, press wmkey+right, press wmkey+a
