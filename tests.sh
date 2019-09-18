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
    python3 execute.py --configdir=example_config --prompt=False --printactions --dryrun --volume=0 --color=False $*  | grep -v -e '^$'
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
    #> press wmkey d, press wmkey pagedown, press wmkey a

# current mode overrides auto-enabled modes
t --modes=focus,vim,term left
    #> press wmkey left

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
    #> execute zsh -c "echo \"good morning\" | festival --tts"

t computer 2 times say hello world
    #> execute zsh -c "echo \"hello world\" | festival --tts", execute zsh -c "echo \"hello world\" | festival --tts"

t computer vim 3 times delete last word
    #> press b, text dw, press b, text dw, press b, text dw

t --modes=zsh computer show files
    #> text ls -l, press enter

t computer show files
    #> run urxvt -e zsh --interactive -c "unset LESS; ls -l | less -r"

t --modes=vim computer control 2 times save
    #> press control s, press control s

t focus change 3 times right
    #> press wmkey d, press wmkey right, press wmkey right, press wmkey right, press wmkey a

t computer define say lol
    #> define { builtin mode computer say lol }
    #> in computer say word+ = in background shell execute echo "$1" | festival --tts 

t computer define print lol
    #> define { builtin print lol }
    #> print <word>+ = 
    #>     def cmd_print(ctx, _, s):
    #>         print(ctx['ecl'].colored(' '.join(util.split_expansion(s)), 'magenta'))

t --modes=zsh 3 times press up
    #> press up, press up, press up
t --modes=zsh press 3 times up
    #> press up, press up, press up
t --modes=zsh press up 3 times
    #> press up, press up, press up

t computer 2 times focus left
    #> press wmkey left, press wmkey left
t computer focus 2 times left
    #> press wmkey left, press wmkey left
t computer focus left 2 times
    #> press wmkey left, press wmkey left
