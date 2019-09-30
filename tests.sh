#!/bin/bash

set -ev

if [ "$#" -ne 1 ]; then
    expected=/tmp/evc-tests-expected-output
    actual=/tmp/evc-tests-actual-output
    grep -oP "^ *(#[>]|t) \K.*" tests.sh > $expected
    ./tests.sh output > $actual
    diff -u $expected $actual
    exit
fi

function run-covered() {
    python3-coverage run --source ecl,eclbuiltins,execute,eclcompletion,util --parallel-mode execute.py $*
}

function t() {
    echo $*
    run-covered --configdir=example_config --prompt=False --dryrun --volume=0 --color=False $*  | grep -v -e '^$'
}

rm -rf htmlcov .coverage*

########################### TEST CASES: ###########################

echo computer print hello | run-covered --configdir=example_config > /dev/null
    # to cover the prompt, color/sound, and process_lines()

# repetition
t computer 3 times print hello world
    #> hello world
    #> hello world
    #> hello world

# arithmetic
t computer arith-demo fibonacci 7
    #> 13

# complex custom types (<target>)
t focus change next work space
    #> pressing wmkey d
    #> pressing wmkey pagedown
    #> pressing wmkey a

# current mode overrides auto-enabled modes
t --modes=focus,vim,urxvt,zsh left
    #> pressing wmkey left

# diagnostic for bad command
t computer focus lol
    #> error: no such command

# equally long but faulty match in non-current mode:
t --modes=vim-find,vim go
    #> pressing enter

# routing through mode map
t computer edit insert text bla
    #> pressing insert
    #> entering text bla

# conditionals
t computer calculate maximum of 2 and 9
    #> 9
t computer calculate maximum of 9 and 2
    #> 9

# quoting
t computer say good morning
    #> executing zsh -c "echo \"good morning\" | festival --tts"

t computer 2 times say hello world
    #> executing zsh -c "echo \"hello world\" | festival --tts"
    #> executing zsh -c "echo \"hello world\" | festival --tts"

t computer vim 3 times delete last word
    #> pressing b
    #> entering text dw
    #> pressing b
    #> entering text dw
    #> pressing b
    #> entering text dw

t --modes=zsh computer show files
    #> entering text ls -l
    #> pressing enter

t computer show files
    #> running urxvt -e zsh --interactive -c "unset LESS; ls -l | less -r"

t --modes=vim computer control 2 times save
    #> pressing control s
    #> pressing control s

t focus change 3 times right
    #> pressing wmkey d
    #> pressing wmkey right
    #> pressing wmkey right
    #> pressing wmkey right
    #> pressing wmkey a

t computer define say lol
    #> in computer say <word>+ = in background shell execute echo "$1" | festival --tts

t computer define print lol
    #> print <word>+ = 
    #>     def cmd_print(ctx, _, s):
    #>         print(ctx['ecl'].colored(' '.join(util.split_expansion(s)), 'magenta'))

t --modes=zsh 3 times press up
    #> pressing up
    #> pressing up
    #> pressing up
t --modes=zsh press 3 times up
    #> pressing up
    #> pressing up
    #> pressing up
t --modes=zsh press up 3 times
    #> pressing up
    #> pressing up
    #> pressing up

t computer 2 times focus left
    #> pressing wmkey left
    #> pressing wmkey left
t computer focus 2 times left
    #> pressing wmkey left
    #> pressing wmkey left
t computer focus left 2 times
    #> pressing wmkey left
    #> pressing wmkey left

t focus change lol
    #> error: expected:
    #> - a <target>: frame ... (1) / new work space (2)
    #> - a <screen>: mexico (3) / germany (4) / india (5)
    #> - a <nextprev>: next ... (6) / previous ... (7)
    #> - a <hdir>: left (8) / right (9)
    #> - a <vdir>: up (10) / down (11)
    #> - a <command> or a <number>

t focus change new
    #> error: did you mean 'work space'?

t computer what time
    #> error: did you mean 'is it'?

t --modes=zsh,computer change
    #> error: expected:
    #> - commands (1)
    #> - directory ... (2)
    #> - replacements (3)

t computer press a press b
    #> pressing a
    #> pressing b

t computer 2 times lol
    #> error: expected a <command>

t --modes test-aliases wrapper
    #> error: command wrapper matched alias:
    #>   test-aliases wrapper = undefined variable
    #> command undefined variable matched alias:
    #>   test-aliases undefined variable = builtin print $nope
    #> undefined variable $nope

t --modes test-aliases wrapper2
    #> error: command wrapper2 matched alias:
    #>   test-aliases wrapper2 = undefined command
    #> command undefined command matched alias:
    #>   test-aliases undefined command = nope
    #> invalid command:
    #>   nope 
    #> expected <command>

t --modes test-aliases undefined subcommand
    #> error: command undefined subcommand matched alias:
    #>   test-aliases undefined subcommand = $(nope)
    #> invalid command:
    #>   nope 
    #> expected <command>

t --modes test-aliases unmatched closing curly
    #> unmatched closing curly: unmatched }

t --modes test-aliases erroneous subcommand
    #> error: command erroneous subcommand matched alias:
    #>   test-aliases erroneous subcommand = $(undefined variable)
    #> command undefined variable matched alias:
    #>   test-aliases undefined variable = builtin print $nope
    #> undefined variable $nope

t computer ktorrent options
    #> in ktorrent: press <word>+, delete download

t --modes=test-aliases ding
    #> error: expected a <vdir>:
    #>   up (1) / down (2)

python3-coverage combine
python3-coverage html
