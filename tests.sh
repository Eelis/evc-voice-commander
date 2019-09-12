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

# repetition
t computer 3 times print hello
    #> nop, mode computer, print hello, mode computer, print hello, mode computer, print hello
    #> hello
    #> hello
    #> hello

# arithmetic
t arith-demo fibonacci 7
    #> 13

# run
t computer calendar
    #> run urxvt -e zsh --interactive -c "cal; sleep 1000"

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

# conditionals
t calculate maximum of 2 and 9
    #> 9
t calculate maximum of 9 and 2
    #> 9

# quoting
t computer say good morning
    #> execute zsh -c "echo '(SayText \"good morning\")' | festival"

t computer 3 times say hello
    #> nop, mode computer, execute zsh -c "echo '(SayText \"hello\")' | festival", mode computer, execute zsh -c "echo '(SayText \"hello\")' | festival", mode computer, execute zsh -c "echo '(SayText \"hello\")' | festival"
