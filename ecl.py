import util
import termcolor
from typing import Dict, List, Tuple, Optional, Callable, Any, TypeVar, Generic

Unit = str # either a literal or a type wrapped in <>
Alternative = Tuple[Unit, bool]
Parameter = List[Alternative]
Form = List[Parameter]
Pattern = List[Form]
Aliases = List[Tuple[Pattern, str]]
Mode = str
Typename = str
Action = Callable
BuiltinCommand = Tuple[Pattern, Optional[Callable], Optional[Action]]

T = TypeVar('T')
U = TypeVar('U')

class ParseResult(Generic[T]):
    longest: int
    error: Optional[str]
    new_mode: Optional[Mode]
    resolved: List[str]
    missing: List[Unit]
    actions: List[Tuple[Action, List[str]]]
    retval: T

    def __init__(self, retval: T):
        self.longest = 0
        self.missing = []
        self.actions = []
        self.new_mode = None
        self.error = None
        self.retval = retval
        self.resolved = []

    def try_improve(self, other: 'ParseResult[T]') -> None:
        if other.longest == self.longest:
            if self.missing or self.error is not None:
                if other.missing:
                    self.missing += other.missing
                else:
                    self.missing = []
                    self.retval = other.retval
        elif other.longest > self.longest:
            self.longest = other.longest
            self.missing = other.missing
            self.actions = other.actions
            self.new_mode = other.new_mode
            self.error = other.error
            self.retval = other.retval
            self.resolved = other.resolved

    def fmap(self, f: Callable[[T], U]) -> 'ParseResult[U]':
        r = ParseResult[U](f(self.retval))
        r.longest = self.longest
        r.missing = self.missing
        r.actions = self.actions
        r.new_mode = self.new_mode
        r.error = self.error
        r.resolved = self.resolved
        return r

def parse_type(s: Unit) -> Optional[Typename]:
    return s[1:-1] if s.startswith('<') else None

def parse_alternative(alt: str) -> Alternative:
    multiple = alt.endswith('+')
    if multiple: alt = alt[:-1]
    return (alt, multiple)

def parse_parameter(param: str) -> Parameter:
    return list(map(parse_alternative, param.split('|')))

def parse_form(form: str) -> Form:
    return list(map(parse_parameter, form.split(' ')))

def parse_pattern(pattern: str) -> Pattern:
    return list(map(parse_form, pattern.split('/')))

def parse_aliases(aliases: Dict[str, str]) -> Aliases:
    return [(parse_pattern(pattern), defn) for pattern, defn in aliases.items()]

class Context():
    modes: Dict[Mode, Aliases]
    color: bool
    script_vars: Dict[str, str]
    always_on_modes: List[Mode]
    builtin_types: Dict[Typename, Callable[[Any], Any]]
    builtin_commands: List[BuiltinCommand]
    global_builtins: List[BuiltinCommand]

    def __init__(self, modes: Dict[Mode, Dict[str, str]], enums: Dict[Typename, Pattern]):
        self.enums = enums
        self.script_vars = {}
        self.color = True
        self.builtin_commands = []
        self.builtin_types = {}
        self.always_on_modes = []

        self.modes = {}
        for mode, raw_aliases in modes.items():
            self.modes[mode] = parse_aliases(raw_aliases)

        # validate patterns and expansions a bit:
        for m, aliases in self.modes.items():
            for pattern, expansion in aliases:
                #if expansion == {}:
                #    expansion = '{}'
                #    aliases[pattern] = expansion
                #if type(expansion) is not str:
                #    raise Exception(mode + ": " + pattern + ": expected string, not " + str(type(expansion)))
                if expansion.startswith('~'):
                    redir = expansion[1:]
                    if redir != 'builtin' and redir not in self.modes:
                        raise Exception(m + ": " + self.render_pattern(pattern) + ": ~" + redir + ": no such mode")
                #for form in pattern:
                #    for param in form:
                #        for t in eclcompletion.types_in_param(param):
                #            if not eclbuiltins.is_builtin_type(t) and not t in enums:
                #                raise Exception(mode + ": " + pattern + ": no such type: " + t)

    def colored(self, s: str, c: str) -> str:
        return termcolor.colored(s, c) if self.color else s

    def italic(self, s: str) -> str: # pragma: no cover
        return util.italic(s) if self.color else s

    def color_mode(self, m: Mode) -> str:
        return self.colored(m, 'cyan')

    def color_commands(self, p: str) -> str:
        return self.colored(p, 'magenta')

    def render_type(self, t: Typename) -> str:
        return util.italic(t) if self.color else '<' + t + '>'

    def render_unit(self, unit: Unit) -> str:
        t = parse_type(unit)
        return unit if t is None else self.render_type(t)

    def render_alternative(self, alt: Alternative) -> str:
        unit, plus = alt
        return self.render_unit(unit) + ('+' if plus else '')

    def render_parameter(self, param: Parameter) -> str:
        return '|'.join(map(self.render_alternative, param))

    def render_form(self, form: Form) -> str:
        return ' '.join(map(self.render_parameter, form))

    def render_pattern(self, pattern: Pattern) -> str:
        return '/'.join(map(self.render_form, pattern))

    def alias_definition_str(self, mode: Mode, pattern: Pattern, expansion: str, start_column: int =0) -> str:
        pat = self.render_pattern(pattern)
        r = self.color_mode(mode) + ' ' + self.color_commands(pat) + ' = '
        indent = start_column + util.column_width(r)
        l = [self.color_commands(e) + ' ' for e in expansion.split()] # todo: handle quoted arguments
        s = l[-1]; l[-1] = s[:-1] # remove last space
        return r + util.indented_and_wrapped(l, indent)

    def match_type(self, args: List[str], type: Typename, enabled_modes: List[Mode]) -> ParseResult[List[str]]:
        bt = self.builtin_types.get(type)
        if bt is not None and bt(args[0]):
            pr = ParseResult[List[str]]([args[0]])
            pr.longest = 1
            return pr
        if type == 'mode' and args[0] in self.modes:
            pr = ParseResult[List[str]]([args[0]])
            pr.longest = 1
            return pr
        x = ParseResult[List[str]]([])
        x.missing = ['<' + type + '>']
        e = self.enums.get(type)
        if e is not None:
            x.try_improve(self.match_pattern(e, args, enabled_modes))
        return x

    def match_simple_parameter(self, param: Parameter, args: List[str], enabled_modes: List[Mode]) -> ParseResult[Optional[str]]:
        arg = args[0]
        r = ParseResult[Optional[str]](None)
        for alt, multiple in param:
            if alt == arg:
                r.longest = 1
                r.missing = []
                r.retval = arg
                break
            type = parse_type(alt)
            if type is not None:
                r.try_improve(self.match_type(args, type, enabled_modes).fmap(lambda x: ' '.join(x)))
        return r

    def match_parameter(self, param: Parameter, args: List[str], enabled_modes: List[Mode]) -> ParseResult[Optional[str]]:
        if param == [('<command>', False)]:
            x = self.match_commands(args, enabled_modes, True, True)
            consumed = list(map(util.quote_if_necessary, args[:x.longest]))
            if x.longest == 0:
                x.retval = None
            elif x.resolved is not None:
                consumed = x.resolved
                if consumed[:1] != ['{']:
                    consumed = ['{'] + consumed + ['}']
                x.retval = ' '.join(consumed)
            x.actions = []
            return x
        elif len(param) == 1 and param[0][1]:
            sub = [(param[0][0], False)]
            pr = ParseResult[Optional[str]](None)
            y = []
            while args and args[0] != ';':
                x = self.match_parameter(sub, args, enabled_modes)
                pr.longest += x.longest
                if x.longest != 0: pr.missing = x.missing
                else: pr.missing += x.missing
                if x.error is not None: pr.error = x.error
                if x.retval is not None: y.append(x.retval)
                if x.retval is None or x.longest == 0 or x.error is not None:
                    break
                args = args[x.longest:]
            pr.retval = ' '.join(map(util.quote_if_necessary, y))
            return pr
        else:
            return self.match_simple_parameter(param, args, enabled_modes)

    def match_params(self, params: List[Parameter], args: List[str], enabled_modes: List[Mode]) -> ParseResult[List[str]]:
        pr = ParseResult[List[str]]([])
        while params and args:
            x = self.match_parameter(params[0], args, enabled_modes)
            pr.longest += x.longest
            if x.longest != 0: pr.missing = x.missing
            if x.error is not None: pr.error = x.error
            if x.retval is None or x.longest == 0: break
            args = args[x.longest:]
            params = params[1:]
            pr.retval.append(x.retval)
        if params and not pr.missing:
            pr.missing = [unit for unit, _ in params[0]]
        return pr

    def match_pattern(self, pattern: Pattern, input: List[str], enabled_modes: List[Mode]) -> ParseResult[List[str]]:
        pr = ParseResult[List[str]]([])
        for form in pattern:
            pr.try_improve(self.match_params(form, input, enabled_modes))
        return pr

    def get_var(self, v: str, vars: List[str]) -> Optional[str]:
        if v.isdigit(): return vars[int(v)]
        return self.script_vars.get(v)

    def substitute_variables(self, expansion: str, vars: List[str], enabled_modes: List[Mode]) -> Tuple[List[str], str, Optional[str]]:
        err = None
        parts: List[str] = []
        append = parts.append
        quoted = False
        while expansion != '':
            if not quoted and expansion.startswith(')'):
                break
            if expansion[0] == '"':
                quoted = not quoted
                append('"')
                expansion = expansion[1:]
            elif not quoted and expansion.startswith('$('):
                sub = expansion[2:]
                args, rest, _err = self.substitute_variables(sub, vars, enabled_modes)
                pr = self.match_commands(args, enabled_modes, True, False)
                consumed = args[:pr.longest]
                unconsumed = args[pr.longest:]
                if pr.error is not None:
                    err = pr.error
                    break
                if pr.missing or pr.longest != len(args):
                    err = self.describe_cmd_parse_result(pr, args)
                    break
                append(str(pr.retval))
                expansion = rest[1:]
            elif expansion.startswith('$'):
                i = 1
                while i < len(expansion) and expansion[i].isalnum():
                    i += 1
                varname = expansion[1:i]
                expansion = expansion[i:]
                x = self.get_var(varname, vars)
                if x is None:
                    err = 'undefined variable $' + varname
                    break
                append(util.escape(x) if quoted else x)
            else:
                append(expansion[0])
                expansion = expansion[1:]
        return (util.split_expansion(''.join(parts)), expansion, err)

    def describe_cmd_parse_result(self, pr: ParseResult, exp) -> str:
        qexp = list(map(util.quote_if_necessary, exp))
        x = [self.colored(s, 'green') + ' ' for s in qexp[:pr.longest]] + \
            [self.colored(s, 'red') + ' ' for s in qexp[pr.longest:]]
        if pr.longest == len(exp): x.append(self.colored('???', 'red'))
        assert pr.missing
        return ('invalid command:\n  ' + util.indented_and_wrapped(x, 3) + '\n' +
               ('missing ' if pr.longest == len(exp) else 'expected ') +
               ' or '.join(map(self.render_unit, pr.missing)) + '\n')

    def match_alias(self, input: List[str],
            enabled_modes: List[Mode],
            input_modes: List[Mode]) -> ParseResult:
        r = ParseResult[Tuple[List[str], Mode, str, Pattern]](([], '', '', []))
        for m in (["default"] if enabled_modes[:1] == ["default"] else enabled_modes):
            for pattern, e in self.modes[m]:
                r.try_improve(self.match_pattern(
                    pattern, input, input_modes).fmap(lambda z: (z, m, e, pattern)))

        if r.longest == 0 or r.missing: return r
        vars, m, expansion, pattern = r.retval

        if expansion == '~builtin':
            return self.match_builtin(input, enabled_modes, False)
        if expansion.startswith('~'):
            mod = expansion[1:]
            return self.match_alias(input, [mod], input_modes)

        r.resolved = vars
        pre = ['{', 'builtin', 'mode', m]
        if vars[:len(pre)] != pre:
            r.resolved = pre + vars + ['}']

        errorpart: Callable[[], str] = lambda: \
            'command ' + self.colored(' '.join(map(util.quote_if_necessary, input[:r.longest])), 'green') + \
            ' matched alias:\n  ' + self.alias_definition_str(m, pattern, expansion, 3) + '\n'

        exp, _rest, err = self.substitute_variables(expansion, vars[:r.longest], enabled_modes)
        if err is not None: r.error = errorpart() + err; return r

        sub = self.match_commands(exp, [m], True, False)
        if sub.error is not None:
            r.error = errorpart() + sub.error
        elif sub.missing or sub.longest != len(exp):
            r.error = errorpart() + self.describe_cmd_parse_result(sub, exp)
        else:
            r.actions = sub.actions
            r.new_mode = sub.new_mode
            r.retval = sub.retval
        return r

    def match_builtin(self, input: List[str], enabled_modes: List[Mode], only_global: bool) -> ParseResult[Any]:
        def nullaction(): pass
        r = ParseResult[Tuple[List[str], Callable, Action, Pattern]](([], nullaction, nullaction, []))
        for pattern, f, act in self.global_builtins:
            r.try_improve(self.match_pattern(
                pattern, input, enabled_modes).fmap(lambda z: (z, f, act, pattern)))
        if not only_global:
            for pattern, f, act in self.builtin_commands:
                r.try_improve(self.match_pattern(
                    pattern, input, enabled_modes).fmap(lambda z: (z, f, act, pattern)))
        vars, f, act, pattern = r.retval

        r2: ParseResult[Any] = r.fmap(lambda _: None)
        if vars is not None:
            r2.resolved = ['builtin'] + vars
            if vars[:1] == ['mode']:
                r2.resolved = []
        if r2.longest != 0 and not r2.missing:
            if f is not None:
                ctx = {'enabled_modes': enabled_modes, 'ecl': self}
                r2.retval = f(ctx, *vars)
            if act is not None: r2.actions = [(act, vars)]
            if pattern == parse_pattern('mode <mode>'): r2.new_mode = vars[1]
                # this applies the mode switch /during/ command evaluation,
                # which is beyond the capabilities of regular built-ins,
                # since those only produce actions to be executed later.
                # hence this special case for the 'mode' command.
        elif input:
            cmd, *args = input
            if cmd == 'builtin':
                r2 = self.match_builtin(args, enabled_modes, False)
                r2.longest += 1 # to account for 'builtin' itself
        return r2

    def match_command(self, words: List[str], enabled_modes: List[Mode], handle_builtins: bool = True) -> ParseResult[Any]:
        if enabled_modes[:1] != ['default']:
            for m in self.always_on_modes:
                if m not in enabled_modes: enabled_modes.append(m)

        pr = self.match_alias(words, enabled_modes, enabled_modes)
        if handle_builtins:
            pr.try_improve(self.match_builtin(words, enabled_modes, True))
        return pr

    def match_commands(self, words: List[str], enabled_modes: List[Mode],
            handle_builtins: bool = True,
            stop_on_semicolon: bool = False) -> ParseResult:
        assert words and words[0] != '}'

        x = util.try_parse_braced_expr(words[0])
        if x is not None and x[1] == '':
            sub = x[0]
            r = self.match_commands(sub, enabled_modes, handle_builtins, False)
            if r.longest == len(sub) and r.error is None and not r.missing:
                r.longest = 1
            else:
                if r.error is None:
                    r.error = self.describe_cmd_parse_result(r, sub)
                r.longest = 0
        else:
            r = self.match_command(words, enabled_modes, handle_builtins)

        if r.longest == 0:
            r.missing = ['<command>']
            r.actions = []
        else:
            if r.longest != len(words) and r.error is None and not r.missing:
                w = words[r.longest:]
                if w and w[0] == ';':
                    if stop_on_semicolon: return r
                    w = w[1:]
                    r.resolved.append(';')
                    r.longest += 1
                if w:
                    if r.new_mode is not None:
                        enabled_modes = [r.new_mode] + [m for m in enabled_modes if m != r.new_mode]
                    r2 = self.match_commands(w, enabled_modes, True, stop_on_semicolon)
                    r.longest += r2.longest
                    r.resolved += r2.resolved
                    r.missing = (r.missing if r2.longest == 0 else []) + r2.missing
                    r.actions += r2.actions
                    if r2.error is not None: r.error = r2.error
                    if r2.longest != 0:
                        if r2.new_mode is not None:
                            r.new_mode = r2.new_mode
                        r.retval = r2.retval
        return r
