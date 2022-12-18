from dataclasses import dataclass
import os

# add `\newcommand{\svgamp}{&}` to use matrix-environments in latex

@dataclass
class Message:
    src: int
    dst: int
    msg: str

@dataclass
class Action:
    actor: int
    action: str
    line_height: float

@dataclass
class Actor:
    display_text: str
    fg_color: str
    bg_color: str
    width: "float | None"


def escape_xml(s:str):
    return (s
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def splitonce(s, split=None):
    a, b, *_ = s.split(split, maxsplit=1) + [""]
    return a, b

# non recursive!
def replace_boundaries(s, start, end, new_start, new_end):
    pos = 0
    while (f1 := s.find(start, pos)) != -1:
        f2 = s.find(end, f1+len(start))
        assert(f2 != -1)
        s2 = s[:f1] + new_start + s[f1+len(start):f2] + new_end
        s = s2 + s[f2+len(end):]
        pos = len(s2)
    return s

# makes latex math mode bold
def make_bold(s: str):
    if "\\boldsymbol" in s or "\\textbf" in s: return s

    s = replace_boundaries(s, "$", "$", "$\\boldsymbol{", "}$")
    s = replace_boundaries(s, "\\text{", "}", "\\textbf{","}")
    #s = f"\\textbf{{{s}}}"

    return s

def fix_amp(s):
    s2 = ""
    backslash_count = 0
    for c in s:
        if c == '\\':
            backslash_count ^= 1
            s2 += c
        elif c == '&' and not backslash_count:
            s2 += "\\svgamp "
        else:
            backslash_count = 0
            s2 += c
    return s2

def convert_to_svg(game_description : str, filename : str, line_offset : int=1) -> str:
    def parsingerror(description, lineno : int, line : str):
        raise Exception(f"Parsing Error: {filename}:{lineno}: {description}\n\t{line}")

    # metrics/layout
    line_height = 20
    name_offset = 1 # in line heights
    action_offset = 2
    actor_width = 140
    msg_width = 100
    msg_height = 20
    msg_txtup = 5 # 4
    leftpad = 10
    botmpad = 20
    rect_ry = 15
    synchronize_actors = False


    actors = [] # Action
    actor_lookup = {} # str -> int

    elements = [] # Message | Action

    lazy_modifiers = []

    DEFAULT_COLORS = ["#ddeeff", "#ffeedd", "#eeffdd", "#ffffdd", "#ffddff"]

    for i_0, l in enumerate(game_description.split('\n')):
        i = i_0 + line_offset
        l = l.strip()
        if not l: continue

        if l[0] == '#': # comment
            continue

        if l[0] == '!': # command
            if l[1:2] == '!':
                cmd, args = "SET", l[2:]
            else:
                cmd, args = splitonce(l[1:])
            # !SET A.width 150
            # !SET [A,B].width 130
            if cmd.upper() == "SET":
                object, fieldvalue = splitonce(args, ".")
                object = object.strip()
                if object[:1] == "[": # multiple objects
                    if object[-1:] != "]": parsingerror("expected matching ']'", i, l) 
                    objects = [a.strip() for a in object[1:-1].split(",")]
                else:
                    objects = [object.strip()]
                field, value = splitonce(fieldvalue)
                
                if field == "": parsingerror("expected field name", i, l)

                # parser, apply
                FIELD_MODIFIERS = {
                    "width":    (float, lambda obj, w: setattr(obj, "width", w)),
                    "fg-color": (str,   lambda obj, c: setattr(obj, "fg_color", c)),
                    "bg-color": (str,   lambda obj, c: setattr(obj, "bg_color", c)),
                }
                
                if field not in FIELD_MODIFIERS:
                    parsingerror(f"unknown field name {field!r}", i, l)

                def do_modify(actor_name, val, mod_apply, i, l):
                    if actor_name not in actor_lookup:
                        parsingerror(f"unknown actor {actor_name!r}", i, l)
                    
                    actor = actors[actor_lookup[actor_name]]
                    mod_apply(actor, val)

                def do_modify_all(val, mod_apply, i, l):
                    for a in actors:
                        mod_apply(a, val)

                mod_parse, mod_apply = FIELD_MODIFIERS[field]
                try:
                    value_parsed = mod_parse(value)
                except ValueError as e:
                    parsingerror(f"invalid value for field {field!r}: {e}", i, l)

                modify_args = (value_parsed, mod_apply, i, l)

                if "*" in objects:
                    lazy_modifiers.append((do_modify_all, modify_args))
                else:
                    for actor_name in objects:
                        lazy_modifiers.append((do_modify, (actor_name, *modify_args)))

                continue


            # default actorwidth
            if cmd.upper() == "ACTORWIDTH":
                actor_width = float(args)
                continue

            if cmd.upper() == "ACTOR":
                name, display_text = splitonce(args)
                if not name: parsingerror("invalid actor name")
                
                fg_color, bg_color = "#000000", DEFAULT_COLORS[len(actors)%len(DEFAULT_COLORS)] #"#dddddd"
                if name[-1] == "]": # additional args
                    lb = name.find("[")
                    if lb == -1: parsingerror("invalid actor name", i, l)

                    args = name[lb+1:-1]
                    name = name[:lb]
                    args = args.split(",")
                    if len(args) != 2: parsingerror("invalid args", i, l)
                    fg_color, bg_color = args

                actor_index = len(actors)
                actors.append(Actor(display_text, fg_color, bg_color, None))
                actor_lookup[name] = actor_index
                continue
            
            parsingerror(f"unknown command {cmd!r}", i, l)
            

        f_colon = l.find(":")
        if f_colon == -1:
            parsingerror("invalid syntax, expected action or message", i, l)

        f_msgl = l.find("<<")
        f_msgr = l.find(">>")
        if f_msgl != -1 and f_msgr != -1:
            if f_msgl < f_msgr: f_msgr = -1
            else:               f_msgl = -1

        if f_msgl != -1 and f_msgl > f_colon: f_msgl = -1
        if f_msgr != -1 and f_msgr > f_colon: f_msgr = -1
        
        if f_msgl != -1 or f_msgr != -1: # message
            f_msg = f_msgl if f_msgl != -1 else f_msgr
            lhs = l[:f_msg].strip()
            rhs = l[f_msg+2:f_colon].strip()

            src, dst = (rhs, lhs) if f_msgl != -1 else (lhs, rhs)

            if src not in actor_lookup:
                parsingerror(f"unknown source actor {src!r}", i, l)
            if dst not in actor_lookup:
                parsingerror(f"unknown destination actor {dst!r}", i, l)
            
            if src == dst:
                parsingerror("source and destination actor cannot be the same", i, l)

            msg = l[f_colon+1:].strip()
            
            elements.append(Message(actor_lookup[src], actor_lookup[dst], msg))
        
        else: # action
            actor = l[:f_colon].strip()
            if not actor: parsingerror("invalid actor", i, l)
            actor_line_height = 1
            if actor[-1] == "]": # additional args, like adjustable line height
                lb = actor.find("[")
                if lb == -1: parsingerror("invalid actor", i, l)
                args = actor[lb+1:-1]
                actor = actor[:lb]

                try: actor_line_height = float(args)
                except ValueError: parsingerror("invalid line height", i, l)


            if actor not in actor_lookup:
                parsingerror(f"unknown actor {actor!r}", i, l)
            
            action = l[f_colon+1:].strip()

            elements.append(Action(actor_lookup[actor], action, actor_line_height))

    
    ##### finished parsing, update lazy properties #####
    for mod, args in lazy_modifiers:
        mod(*args)

    ##### build svg #####
    # build content first, prepend frames of games at the end, wrap it into svg

    actor_cursors = [action_offset*line_height]*len(actors)
    actor_prev_was_msg = [True]*len(actors)
    message_cursors = [action_offset/2*line_height]*(len(actors)-1)

    draw_elements = ""
    text_elements = ""

    stroke_width = 1 #0.75

    def text(x, y, adjust, color, text, bold=False, italic=False):
        anchor = {"center": "middle", "left": "start", "right": "end"}[adjust]
        align = {"center": "center", "left": "start", "right": "end"}[adjust]
        more_style = ""
        if bold: more_style += ";font-weight:bold"
        if italic: more_style += ";font-style:italic"

        content = escape_xml(fix_amp(text))
        return f"""<text style="text-align:{align};text-anchor:{anchor};fill:{color}{more_style}" x="{x}" y="{y}">{content}</text>\n"""

    def line(x0, y0, x1, y1):
        #return f"""<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}" stroke="black" />\n"""
        return f"""<line x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}" style="stroke:#000000;stroke-width:{stroke_width}px" />\n"""

    # x, y in alternating order
    def path(*points):
        assert points and len(points) % 2 == 0
        d = "M" + " ".join(f"{x},{y}" for x,y in zip(points[0::2],points[1::2]))
        return f"""<path d="{d}" style="fill:none;stroke:#000000;stroke-width:{stroke_width}px" />\n"""

    def arrow(x0, y0, x1, y1):
        t = 5
        e = 0.5
        x11 = x1+e if x1 < x0 else x1-e
        x1d = x1+t+e if x1 < x0 else x1-t-e
        return (
            line(x0, y0, x1, y1) +
            path(x1d, y0-t, x11, y0, x1d, y0+t)
        )

    def rect(x, y, w, h, ry, color):
        return f"""<rect style="fill:{color};stroke:#000000;stroke-width:{stroke_width}px" width="{w}" height="{h}" x="{x}" y="{y}" ry="{ry}" />\n"""

    def actor_left(i):
        #return i*(actor_width+msg_width)
        return sum((a.width or actor_width) + msg_width for a in actors[:i])
    
    def actor_right(i):
        #return actor_left(i)+actor_width
        return actor_left(i) + (actors[i].width or actor_width)

    def actor_center(i):
        return (actor_left(i)+actor_right(i))/2

    for i, actor in enumerate(actors):
        text_elements += text(actor_center(i), line_height*name_offset,
            adjust="center", 
            color=actor.fg_color,
            text=make_bold(actor.display_text),
            bold=True)

    for e in elements:
        if isinstance(e, Message):
            s, d = e.src, e.dst
            """
            if synchronize_actors:
                cursor = max(actor_cursors[s], actor_cursors[d])
                actor_cursors[s] = actor_cursors[d] = cursor+msg_height
            else:
                cursor = max(actor_cursors[s], actor_cursors[d])
                if not actor_prev_was_msg[s]: actor_cursors[s] += msg_height
                if not actor_prev_was_msg[d]: actor_cursors[d] += msg_height
            actor_prev_was_msg[s]=actor_prev_was_msg[d] = False
            """
            m = min(s, d)
            #cursor = max(actor_cursors[s], actor_cursors[d], message_cursors[m])
            cursor = max(actor_cursors[s], message_cursors[m])
            actor_cursors[d] = max(actor_cursors[d], cursor)
            message_cursors[m] = cursor+msg_height

            if s < d: # left arrow
                sx = actor_right(s)
                dx = actor_left(d)
            else:
                sx = actor_left(s)
                dx = actor_right(d)

            y = cursor+msg_height/2
            draw_elements += arrow(sx, y, dx, y)
            text_elements += text((sx+dx)/2, y-msg_txtup,
                adjust="center", 
                color="#000000",
                text=e.msg)#f"{{\\footnotesize {e.msg}}}")

        elif isinstance(e, Action):
            cursor = actor_cursors[e.actor]
            actor_cursors[e.actor] = cursor + e.line_height*line_height
            y = cursor+(0.5+e.line_height/2)*line_height

            if action := e.action:
                bold = False
                italic = False

                def parse_whole_bi(s, n):
                    s=s.strip()
                    if s.startswith("*"*n):
                        return s[n:].rstrip("*")
                    if s.startswith("_"*n):
                        return s[n:].rstrip("_")

                center = False
                if action[:1] == action[-1:] == '°':
                    action = action[1:-1]
                    center = True

                while action_bold := parse_whole_bi(action, 2):
                    action = action_bold
                    bold = True
                
                while action_it := parse_whole_bi(action, 1):
                    action = action_it
                    italic = True

                text_elements += text(
                    x=actor_center(e.actor) if center else actor_left(e.actor)+leftpad,
                    y=y,
                    adjust="center" if center else "left",
                    color=actors[e.actor].fg_color,
                    text=action,
                    bold=bold,
                    italic=italic)
            actor_prev_was_msg[e.actor] = True

    svgw = actor_right(len(actors)-1)
    svgh = max(actor_cursors)+botmpad
    
    # put boundaries around actors
    rect_elements = ""
    for i, actor in enumerate(actors):
        rect_elements += rect(actor_left(i), 0, actor.width or actor_width, svgh, rect_ry, actor.bg_color)

    svg = rect_elements + draw_elements + text_elements

    svg = f"""<svg viewBox="-0.5 -0.5 {svgw+1} {svgh+1}" xmlns="http://www.w3.org/2000/svg">\n{svg}</svg>\n"""
    
    return svg



def create_game_pdf_tex_i(out_filename_prefix: str, description: str, fn_in: str, line_offset: int=1):
    fn_svg = f"{out_filename_prefix}.svg"
    fn_pdf = f"{out_filename_prefix}.pdf"

    svg = convert_to_svg(description, fn_in, line_offset) # throws

    files = [(fn_svg, svg)]
    tasks = [f"inkscape --file={fn_svg} --export-pdf={fn_pdf} --export-latex"]

    return files, tasks


def complete_files_tasks(files, tasks):
    for filename, content in files:
        print(f"writing {filename}")
        with open(filename, "wt") as f:
            f.write(content)

    for task in tasks:
        print(task)
        os.system(task)

def create_game_pdf_tex(out_filename_prefix: str, description: str, fn_in: str, line_offset: int=1):
    files, tasks = create_game_pdf_tex_i(out_filename_prefix, description, fn_in, line_offset)
    complete_files_tasks(files, tasks)

if __name__=="__main__":
    # eg.: python3 game.py game2.txt -o game2.svg
    from sys import argv
    if len(argv) != 4 or argv[2] != "-o":
        print(f"Usage {argv[0]} <input> -o [<output.svg>|<output.pdf>]")
        exit(1)

    fn_in = argv[1]
    fn_out = argv[3]
    is_svg = fn_out.endswith(".svg")
    is_pdf = fn_out.endswith(".pdf")
    if not is_svg and not is_pdf:
        print("Output file either needs to be an SVG or PDF file")
        exit(1)
    
    fn_prefix = fn_out[:-4]

    with open(fn_in, "rt") as f: description = f.read()
    
    if is_pdf:
        create_game_pdf_tex(fn_prefix, description, fn_in)

    else:
        content = convert_to_svg(description, fn_in) # throws
        complete_files_tasks([(fn_out, content)],[])        
