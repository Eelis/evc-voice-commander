import util
import termcolor

class ParseResult():
    def __init__(self, retval=None):
        self.longest = 0
        self.missing = []
        self.actions = []
        self.new_mode = None
        self.error = None
        self.retval = retval

    def try_improve(self, other):
        if other.longest == self.longest:
            if other.missing != [] and self.missing != []:
                self.missing += other.missing
            elif self.missing != []:
                self.missing = []
                self.retval = other.retval
        elif other.longest > self.longest:
            self.longest = other.longest
            self.missing = other.missing
            self.actions = other.actions
            self.new_mode = other.new_mode
            self.error = other.error
            self.retval = other.retval

def is_global_builtin_pattern(pat):
    global_builtins = ['options', 'define', 'builtin']
    pat = pat.split()
    while pat != [] and pat[0][0] == '<': pat = pat[1:]
    return pat != [] and pat[0] in global_builtins

def forms(pattern): return pattern.split('/')
def params(form): return form.split(' ')
def alternatives(param): return param.split('|')

class Context():
    def __init__(self):
        self.modes = {}
        self.enums = {}
        self.script_vars = {}
        self.color = True
        self.builtin_commands = {}
        self.builtin_types = {}

    def colored(self, s, c):     return termcolor.colored(s, c) if self.color else s
    def italic(self, s):         return util.italic(s) if self.color else s
    def color_mode(self, m):     return self.colored(m, 'cyan')
    def color_commands(self, p): return self.colored(p, 'magenta')

    def italic_types(self, pattern):
        return '/'.join(
                [' '.join(
                    ['|'.join(
                        [ (self.italic(alt[1:-1]) if alt.startswith('<') else alt)
                            for alt in alternatives(param)
                        ])
                        for param in params(form)
                    ])
                    for form in forms(pattern)])

    def alias_definition_str(self, mode, pattern, start_column=0):
        expansion = self.modes[mode][pattern]
        pat = self.italic_types(pattern)
        r = self.color_mode(mode) + ' ' + self.color_commands(pat) + ' = '
        indent = start_column + len(mode) + len(util.strip_markup(pat)) + len("  = ")
        l = [self.color_commands(e) + ' ' for e in expansion.split()] # todo: handle '' args
        s = l[-1]; l[-1] = s[:-1] # remove last space
        return r + util.indented_and_wrapped(l, indent)

    def match_type(self, param, args, type, enabled_modes):
        if type in self.builtin_types and self.builtin_types[type](args[0]):
            return (1, [])
        if type == 'mode' and args[0] in self.modes:
            return (1, [])
        x = ParseResult()
        x.missing = [param]
        if type in self.enums:
            x.try_improve(self.match_pattern(self.enums[type], args, enabled_modes))
        return (x.longest, x.missing)

    def match_simple_parameter(self, param, args, enabled_modes):
        arg = args[0]
        for alt in alternatives(param):
            if alt == arg: return (1, [])
            if alt.startswith('<'):
                type = alt[1:-1]
                x, y = self.match_type(param, args, type, enabled_modes)
                if x != 0: return (x, y)
        return (0, [param])

    def match_parameter(self, param, args, enabled_modes, i):
        upr = ParseResult(([], [], i))
        if args[:1] == ['evaluate']:
            sub = args[1:]
            x = self.match_command(sub, enabled_modes, True)
            x.retval = ([str(x.retval)] + sub[x.longest:], [], i)
            upr.try_improve(x)
                # not i+1 because still on same parameter
                # we would need to add 1 to pr.longest to account for having consumed 'evaluate',
                # but this is canceled out by a -1 to account for the newly inserted argument.
        if param == '<command>':
            x = self.match_command(args, enabled_modes, True)
            x.retval = (args[x.longest:]
               , [enabled_modes[0], ' '.join(map(util.quote_if_necessary, args[:x.longest]))]
               , i + 1)
            upr.try_improve(x)
        elif param == '<words>':
            x = ParseResult(([], [' '.join(map(util.quote_if_necessary, args))], i + 1))
            x.longest = len(args)
            upr.try_improve(x)
        else:
            x = ParseResult()
            x.longest, x.missing = self.match_simple_parameter(param, args, enabled_modes)
            x.retval = (args[x.longest:], [' '.join(args[:x.longest])], i + 1)
            upr.try_improve(x)
        return upr

    def match_params(self, params, args, enabled_modes):
        pr = ParseResult()
        pr.retval = []
        i = 0
        while i < len(params) and args != [] and pr.missing == []:
            x = self.match_parameter(params[i], args, enabled_modes, i)
            args, vars_here, i = x.retval
            pr.retval += vars_here
            pr.longest += x.longest
        if i < len(params) and pr.missing == []:
            pr.missing = [params[i]]
        return pr

    def match_pattern(self, pattern, input, enabled_modes):
        pr = ParseResult()
        for form in forms(pattern):
            pr.try_improve(self.match_params(params(form), input, enabled_modes))
        return pr

    def substitute_variables(self, expansion, vars):
        nvars = self.script_vars.copy()
        nvars['*'] = ' '.join(map(util.quote_if_necessary, vars))
        for i, v in enumerate(vars): nvars[str(i)] = v
        err = None
        replaced = ''
        quoted = False
        while expansion != '':
            if expansion[0] == '"':
                quoted = not quoted
                replaced += '"'
                expansion = expansion[1:]
            elif expansion.startswith('$'):
                i = 1
                while i < len(expansion) and (expansion[i].isalnum() or expansion[i] == '*'):
                    i += 1
                varname = expansion[1:i]
                expansion = expansion[i:]
                if varname not in nvars:
                    err = 'undefined variable $' + varname
                    break
                replaced += (util.escape(nvars[varname]) if quoted else nvars[varname])
            else:
                replaced += expansion[0]
                expansion = expansion[1:]
        return (util.split_expansion(replaced), err)

    def match_alias(self, input, enabled_modes):
        r = ParseResult((None, None, None, None))
        for m in enabled_modes:
            for pattern, exp in self.modes[m].items():
                x = self.match_pattern(pattern, input, enabled_modes)
                x.retval = (x.retval, m, exp, pattern)
                r.try_improve(x)

        r.new_mode = enabled_modes[0]
        if r.longest == 0 or r.missing != []: return r
        vars, m, expansion, pattern = r.retval

        errorpart = 'command ' + self.colored(' '.join(input[:r.longest]), 'green') + ' matched alias:\n' + \
                    '  ' + self.alias_definition_str(m, pattern, 4) + '\n'

        exp, err = self.substitute_variables(expansion, vars[:r.longest])
        if err is not None:
            r.error = errorpart + self.colored(err, 'red')
            return r

        sub = self.match_command(exp, [m], True)
        if sub.missing == []:
            r.actions = sub.actions
            r.new_mode = sub.new_mode
            r.retval = sub.retval # todo: maybe there are better choices here
            if sub.error is not None:
                r.error = errorpart + sub.error
        else:
            qexp = list(map(util.quote_if_necessary, exp))
            s = util.indented_and_wrapped(
                [self.colored(s, 'green') + ' ' for s in qexp[:sub.longest]] +
                [self.colored(s, 'red') + ' ' for s in qexp[sub.longest:]], 4)
            r.error = errorpart + \
                '  invalid expansion:\n    ' + s + '\n' + \
                '  ' + ('missing ' if sub.longest == len(exp) else 'expected ') + \
                ' or '.join(map(self.italic_types, sub.missing)) + '\n'
        return r

    def match_builtin(self, input, enabled_modes, only_global):
        r = ParseResult((None, None, None, None))
        for pattern, (f, act) in self.builtin_commands.items():
            if not only_global or is_global_builtin_pattern(pattern):
                y = self.match_pattern(pattern, input, enabled_modes)
                y.retval = (y.retval, f, act, pattern)
                r.try_improve(y)
        vars, f, act, pattern = r.retval
        r.retval = None
        if r.longest != 0 and r.missing == []:
            if f is not None:
                ctx = {'enabled_modes': enabled_modes}
                r.retval = f(ctx, *vars)
            if act is not None: r.actions = [(act, vars)]
            if pattern == 'mode <mode>': r.new_mode = vars[1]
                # this applies the mode switch /during/ command evaluation,
                # which is beyond the capabilities of regular built-ins,
                # since those only produce actions to be executed later.
                # hence this special case for the 'mode' command.
        elif input != []:
            cmd, *args = input
            if cmd == 'builtin':
                r = self.match_builtin(args, enabled_modes, False)
                r.longest += 1 # to account for 'builtin' itself
        return r

    def match_command(self, words, enabled_modes, handle_builtins=True):
        r = self.match_alias(words, enabled_modes)
        if handle_builtins and r.error is None:
            r.try_improve(self.match_builtin(words, enabled_modes, True))
        if r.longest == 0:
            r.missing = ['<command>']
            r.actions = []
            r.new_mode = enabled_modes[0]
        else:
            if r.new_mode is not None:
                enabled_modes[0] = r.new_mode
            if r.longest != len(words) and r.error is None:
                r2 = self.match_command(words[r.longest:], enabled_modes, True)
                r.longest += r2.longest
                r.missing = r2.missing
                r.actions += r2.actions
                r.new_mode = r2.new_mode
                r.error = r2.error
                r.retval = r2.retval
        return r
