import ecl
import subprocess
import util
from typing import Dict, List, Tuple, Optional

class Suggestions:
    literals: List[Tuple[List[str], bool]]
    types_with_sugs: List[Tuple[ecl.Typename, List[Tuple[List[str], bool]]]]
    types_without_sugs: List[ecl.Typename]

def linear_suggestions(sugs: Suggestions) -> List[List[str]]:
    return [x for x, _ in sugs.literals] + [x for _, l in sugs.types_with_sugs for x, _ in l]

def only_choice(sugs: Suggestions):
    if sugs.types_without_sugs: return None
    if len(sugs.literals) == 1 and sugs.types_with_sugs == []:
        return sugs.literals[0][0]
    return None

def types_in_unit(unit: ecl.Unit) -> List[ecl.Typename]:
    t = ecl.parse_type(unit)
    return [] if t is None else [t]

def types_in_alternative(alt: ecl.Alternative) -> List[ecl.Typename]:
    return types_in_unit(alt[0])

def types_in_param(param: ecl.Parameter) -> List[ecl.Typename]:
    return [t for alt in param for t in types_in_alternative(alt)]

def literals_in_unit(unit: ecl.Unit) -> List[str]:
    return [unit] if ecl.parse_type(unit) is None else []

def literals_in_param(param: ecl.Parameter) -> List[str]:
    return [x for unit, _ in param for x in literals_in_unit(unit)]

def definite_missing_arguments(
        context: ecl.Context, goodwords, enabled_modes, handle_builtins: bool) -> Tuple[List[str], bool]:
    more: List[str] = []
    incomplete = True
    while True:
        pr = context.match_commands(goodwords + more, enabled_modes, handle_builtins)
        if pr.longest == len(goodwords + more) and pr.error is None and pr.missing == []:
            incomplete = False
            break
        if pr.longest < len(goodwords) + len(more): break
        if pr.missing == [] or pr.error is not None: break
        sugs = get_suggestions(context, goodwords + more, pr.missing, enabled_modes, handle_builtins)
        c = only_choice(sugs)
        if c is None: break
        more += c
    return (more, incomplete)

def get_suggestions(context, goodwords, missing: List[ecl.Unit], enabled_modes, handle_builtins) -> Suggestions:
    sugs = Suggestions()
    sugs.literals = []
    sugs.types_with_sugs = []
    sugs.types_without_sugs = []
    if missing == []: return sugs

    # find all types the command could continue with:
    types_todo: List[str] = [t for unit in missing for t in types_in_unit(unit)]
    types_done: List[str] = []
    while types_todo != []:
        t, *types_todo = types_todo
        if t in types_done: continue
        types_done.append(t)
        if t in context.enums:
            for form in context.enums[t]:
                types_todo += types_in_param(form[0])

    # find their completions:
    rt = []
    for type in types_done:
        l: List[str] = []
        if type in context.completions:
            l = subprocess.Popen(context.completions[type], shell=True,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL).stdout.read().decode('utf-8').strip().split('\n')
        if type in context.enums:
            for form in context.enums[type]:
                l += literals_in_param(form[0])
        if l != [] or type not in context.enums:
            ul: List[Tuple[List[str], bool]] = []
            for x in l:
                more, incomplete = definite_missing_arguments(context, goodwords + [x], enabled_modes, handle_builtins)
                ul.append(([x] + more, incomplete))
            rt.append((type, ul))

    # get literals (that aren't already listed for one of the types):
    lits = list(set(
        [l for unit in missing
            for l in literals_in_unit(unit)
             if not any([l == y for _, x in rt for y, _ in x])]))
    lits.sort()

    # extend literals
    for x in lits:
        y, incomplete = definite_missing_arguments(context, goodwords + [x], enabled_modes, handle_builtins)
        sugs.literals.append(([x] + y, incomplete))

    # partition types by whether they have suggestions:
    sugs.types_with_sugs = [(x, l) for x, l in rt if l != []]
    sugs.types_without_sugs = [x for x, l in rt if l == []]

    return sugs

def print_suggestions(eclc, suggestions: Suggestions):
    if len(suggestions.literals) == 1 and suggestions.types_with_sugs == [] and suggestions.types_without_sugs == []:
        print(eclc.colored("error: did you mean '" + ' '.join(suggestions.literals[0][0]) + "'?", 'red'))
    elif suggestions.literals == [] and len(suggestions.types_without_sugs) == 1 and suggestions.types_with_sugs == []:
        t = suggestions.types_without_sugs[0]
        print(eclc.colored('error: expected ' + util.a_or_an(t) + ' ' + eclc.render_type(t), 'red'))
    elif suggestions.literals == [] and suggestions.types_without_sugs == [] and len(suggestions.types_with_sugs) == 1:
        t, sugs = suggestions.types_with_sugs[0]
        print(eclc.colored('error: expected ' + util.a_or_an(t) + ' ' + eclc.render_type(t) + ':\n  ', 'red'), end='')
        i = 1
        l = []
        for s, more in sugs:
            y = eclc.color_commands(' '.join(s)) + ' '
            if more: y += '... '
            y += '(' + str(i) + ')'
            i += 1
            l.append(y)
            l.append(' / ')
        print(util.indented_and_wrapped(l[:-1], 2))
    else:
        print(eclc.colored('error: expected:', 'red'))
        i = 1
        for l, incomplete in suggestions.literals:
            print('-', eclc.color_commands(' '.join(l)), end='')
            if incomplete: print(' ...', end='')
            print(' (' + str(i) + ')')
            i += 1
        for t, sugs in suggestions.types_with_sugs:
            x = '- ' + util.a_or_an(t) + ' ' + eclc.color_commands(eclc.render_type(t)) + ': '
            print(x, end='')
            l = []
            for s, more in sugs:
                y = eclc.color_commands(' '.join(s)) + ' '
                if more: y += '... '
                y += '(' + str(i) + ')'
                i += 1
                l.append(y)
                l.append(' / ')
            print(util.indented_and_wrapped(l[:-1], util.column_width(x)))
        if suggestions.types_without_sugs != []:
            print('-', util.commas_or([util.a_or_an(t) + ' ' + eclc.color_commands(eclc.render_type(t)) for t in suggestions.types_without_sugs]))
