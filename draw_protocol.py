from dataclasses import dataclass
import os
from typing import Tuple

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
    line_height: "float | None"

@dataclass
class Actor:
    display_text: str
    fg_color: str
    bg_color: str
    hl_color: "str | None" = None
    width: "float | None" = None
    box_visible: bool = True
    title_line: bool = True
    message_space_right: "float | None" = None


def or_default(value, default):
    return value if value is not None else default

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

# makes LaTeX math mode bold
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



INCLUDE_PATHS = [
    os.path.dirname(os.path.abspath(__file__)),
]


def is_path_relative(filename):
    filename.replace(os.sep, "/")
    return filename.startswith("./") or filename.startswith("../")

def is_path_absolute(filename):
    filename.replace(os.sep, "/")

    if filename.startswith("/"): return True

    # check if drive
    if len(filename) >= 2 and 'A' <= filename[0].upper() <= 'Z' and filename[1] == ":": return True
    
    return False

def find_include_file(filename):
    if not is_path_relative(filename) and not is_path_absolute(filename):
        for ip in INCLUDE_PATHS:
            a_path = os.path.join(ip, filename)
            if os.path.exists(a_path):
                return a_path
    return filename

LineLocation = Tuple[str, int]


def convert_to_svg(game_description : str, filename : str, line_offset : int=1) -> str:
    def parsingerror(description, location : LineLocation, line : str):
        filename, lineno = location
        raise Exception(f"Parsing Error: {filename}:{lineno}: {description}\n\t{line}")

    # Push Message or Action, or throw syntax error
    def parse_message_or_action(loc : LineLocation, l : str):
        f_colon = l.find(":")
        if f_colon == -1:
            parsingerror("invalid syntax, expected action or message", loc, l)

        text = l[f_colon+1:].strip()
        str_actors = l[:f_colon].strip()

        is_left  = "<<" in str_actors
        is_right = ">>" in str_actors

        if is_left and is_right:
            parsingerror("message cannot be sent into multiple directions", loc, l)

        if is_left or is_right: # message
            actors = str_actors.split("<<" if is_left else ">>")

            if is_left: actors = list(reversed(actors))

            for a in actors:
                if a not in actor_lookup:
                    parsingerror(f"unknown actor {a!r}", loc, l)

            if len(set(actors)) != len(actors):
                parsingerror("source and destination actor cannot be the same", loc, l)

            msg = text
            
            actor_indices = [actor_lookup[a] for a in actors]

            # TODO: elements.append(Message(actor_indices, msg))

            for src, dst in zip(actor_indices[:-1], actor_indices[1:]):
                elements.append(Message(src, dst, msg))

        
        else: # action
            actor = l[:f_colon].strip()
            if not actor: parsingerror("invalid actor", loc, l)
            actor_line_height = None
            if actor[-1] == "]": # additional args, like adjustable line height
                lb = actor.find("[")
                if lb == -1: parsingerror("invalid actor", loc, l)
                args = actor[lb+1:-1]
                actor = actor[:lb]

                try: actor_line_height = float(args)
                except ValueError: parsingerror("invalid line height", loc, l)


            if actor not in actor_lookup:
                parsingerror(f"unknown actor {actor!r}", loc, l)
            
            action = text

            elements.append(Action(actor_lookup[actor], action, actor_line_height))


    # metrics/layout
    line_height = 20
    name_offset = 1 # in line heights
    action_offset = 1.5 # 2
    actor_width = 140
    msg_width = 100
    msg_height = 20
    msg_txtup = 5 # 4
    leftpad = 10
    botmpad = 20
    rect_ry = 10 #15
    synchronize_actors = False


    actors = [] # Action
    actor_lookup = {} # str -> int

    elements = [] # Message | Action

    lazy_modifiers = []

    DEFAULT_COLORS = ["#ddeeff", "#ffeedd", "#eeffdd", "#ffffdd", "#ffddff"]
    DEFAULT_HIGHLIGHT_COLORS = ["#77aaff", "#ffaa77", "#77ddaa", "#ffff77", "#ff77ff"]

    line_color = "black" # default color for messages and borders of actors

    include_file = None 
    def line_stream(line_offset, filename, code):
        nonlocal include_file
        for i_0, l in enumerate(code.split('\n')):
            yield (i_0 + line_offset, filename), l

            while include_file is not None:
                inc_filename, include_file = include_file, None
                with open(find_include_file(inc_filename), "rt") as f:
                    included_content = f.read()

                yield from line_stream(1, inc_filename, included_content)

    for loc, l in line_stream(line_offset, filename, game_description):
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
                    if object[-1:] != "]": parsingerror("expected matching ']'", loc, l) 
                    objects = [a.strip() for a in object[1:-1].split(",")]
                else:
                    objects = [object.strip()]
                field, value = splitonce(fieldvalue)
                
                if field == "": parsingerror("expected field name", loc, l)

                none = lambda s:None
                def color(c):
                    colors = DEFAULT_COLORS
                    if c[0] == "h":
                        c = c[:1]
                        colors = DEFAULT_HIGHLIGHT_COLORS
                    try: i = int(c)
                    except ValueError: return c
                    return (colors)[i%(len(colors))]

                def boolean(c):
                    VALUES = {"0": False, "1": True, "false": False, "true": True}
                    try: return VALUES[c.lower()]
                    except KeyError:
                        raise ValueError(f"Invalid boolean value {c!r}")

                # name: (parser, apply)
                FIELD_MODIFIERS = {
                    "width":      (float,   lambda obj, w: setattr(obj, "width", w)),
                    "space":      (float,   lambda obj, w: setattr(obj, "message_space_right", w)),
                    "fg-color":   (color,   lambda obj, c: setattr(obj, "fg_color", c)),
                    "bg-color":   (color,   lambda obj, c: setattr(obj, "bg_color", c)),
                    "hl-color":   (color,   lambda obj, c: setattr(obj, "hl_color", c)),
                    "title-line": (boolean, lambda obj, b: setattr(obj, "title_line", b)),
                    "box":        (boolean, lambda obj, b: setattr(obj, "box_visible", b)),
                    "0":          (none,    lambda obj, _: (setattr(obj, "box_visible", False), setattr(obj, "width", 0.0))),
                }
                
                if field not in FIELD_MODIFIERS:
                    parsingerror(f"unknown field name {field!r}", loc, l)

                def do_modify(actor_name, val, mod_apply, loc, l):
                    if actor_name not in actor_lookup:
                        parsingerror(f"unknown actor {actor_name!r}", loc, l)
                    
                    actor = actors[actor_lookup[actor_name]]
                    mod_apply(actor, val)

                def do_modify_all(val, mod_apply, loc, l):
                    for a in actors:
                        mod_apply(a, val)

                mod_parse, mod_apply = FIELD_MODIFIERS[field]
                try:
                    value_parsed = mod_parse(value)
                except ValueError as e:
                    parsingerror(f"invalid value for field {field!r}: {e}", loc, l)

                modify_args = (value_parsed, mod_apply, loc, l)

                if "*" in objects:
                    lazy_modifiers.append((do_modify_all, modify_args))
                else:
                    for actor_name in objects:
                        lazy_modifiers.append((do_modify, (actor_name, *modify_args)))

                continue


            # default actorwidth
            if cmd.upper() == "ACTORWIDTH":
                print("Warning: '!ACTORWIDTH' is deprecated and might be removed")
                actor_width = float(args)
                continue

            if cmd.upper() == "LINECOLOR":
                print("Warning: The command '!LINECOLOR' is experimental and might be changed")
                line_color = args
                continue

            if cmd.upper() == "DEFAULT_COLORS":
                print("Warning: The command '!DEFAULT_COLORS' is experimental and might be changed")
                DEFAULT_COLORS = args.split()
                continue

            if cmd.upper() == "DEFAULT_HIGHLIGHT_COLORS":
                print("Warning: The command '!DEFAULT_HIGHLIGHT_COLORS' is experimental and might be changed")
                DEFAULT_HIGHLIGHT_COLORS = args.split()
                continue

            if cmd.upper() == "ACTOR":
                name, display_text = splitonce(args)
                if not name: parsingerror("invalid actor name", loc, l)
                
                fg_color, bg_color = "#000000", DEFAULT_COLORS[len(actors)%len(DEFAULT_COLORS)] #"#dddddd"
                hl_color = None
                #bg_color, hl_color = "#ffffff", DEFAULT_HIGHLIGHT_COLORS[len(actors)%len(DEFAULT_HIGHLIGHT_COLORS)]
                #hl_color = "#ffffff"
                if name[-1] == "]": # additional args
                    lb = name.find("[")
                    if lb == -1: parsingerror("invalid actor name", loc, l)

                    args = name[lb+1:-1]
                    name = name[:lb]
                    args = args.split(",")
                    if len(args) != 2: parsingerror("invalid args", loc, l)
                    fg_color, bg_color = args

                actor_index = len(actors)
                actors.append(Actor(display_text, fg_color, bg_color, hl_color))
                actor_lookup[name] = actor_index
                continue
            
            if cmd.upper() == "INCLUDE":
                include_file = args
                # line_stream now yields the contents of the file
                continue


            parsingerror(f"unknown command {cmd!r}", loc, l)
            

        parse_message_or_action(loc, l)

    
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


    css_light_styles = ""
    css_dark_styles = ""
    color_classes = {}
    style_class_index = 0
    # return {css_property: ([classes...], style)}
    def themed_color(css_property, color):
        nonlocal css_light_styles, css_dark_styles
        nonlocal style_class_index, color_classes
        if ":" not in color:
            return {css_property: ("", color)}

        # light:dark
        if (css_property, color) in color_classes:
            return {css_property: (color_classes[css_property, color], "")}

        light_color, dark_color = color.split(":", maxsplit=1)

        style_class_index += 1
        class_name = f"style{style_class_index}"  
        css_light_styles += f".{class_name} {{{css_property}:{light_color};}}\n"
        css_dark_styles += f".{class_name} {{{css_property}:{dark_color};}}\n"
        color_classes[css_property, color] = class_name
        return {css_property: (class_name, "")}



    def svg_tag(name, **properties):
        if "style" in properties and isinstance(properties["style"], dict):
            properties = properties.copy()

            def unpack_style(v):
                # for color tuples `light:dark`
                if isinstance(v, tuple): return v[1]
                return v
            
            def unpack_classes(v):
                if isinstance(v, tuple): return v[0]
                return ""

            properties["class"] = " ".join(
                unpack_classes(v) for k, v in properties["style"].items() if unpack_classes(v)
            )

            properties["style"] = ";".join(
                f"{k}:{unpack_style(v)}" for k, v in properties["style"].items() if unpack_style(v)
            )

        properties = " ".join(
            f'{k}="{v}"'
            for k, v in properties.items() if v != ""
        )
        
        def expect_content(content=None):
            if content is not None:
                return f"<{name} {properties}>{content}</{name}>\n"
            else:
                return f"<{name} {properties} />\n"

        return expect_content


    def text(x, y, adjust, color, text, bold=False, italic=False):
        anchor = {"center": "middle", "left": "start", "right": "end"}[adjust]
        align = {"center": "center", "left": "start", "right": "end"}[adjust]

        return svg_tag("text", 
            style={
                "text-align": align,
                "text-anchor": anchor,
                "font-weight":"bold"*bold,
                "font-style":"italic"*italic,
                **themed_color("fill", color),
            },
            x=x,
            y=y,
        )(content=escape_xml(fix_amp(text)))


    def line(x0, y0, x1, y1, color):
        return svg_tag("line",
            x1=x0, y1=y0,
            x2=x1, y2=y1,
            style={
                **themed_color("stroke", color),
                "stroke_width": f"{stroke_width}px",
            }
        )()


    # x, y in alternating order
    def path(*points, color):
        assert points and len(points) % 2 == 0
        d = "M" + " ".join(f"{x},{y}" for x,y in zip(points[0::2],points[1::2]))
        return svg_tag("path",
            d=d,
            style={
                "fill":"none",
                **themed_color("stroke", color),
                "stroke-width":f"{stroke_width}px",
            }
        )()


    def arrow(x0, y0, x1, y1, color):
        t = 5
        e = 0.5
        x11 = x1+e if x1 < x0 else x1-e
        x1d = x1+t+e if x1 < x0 else x1-t-e
        return (
            line(x0, y0, x1, y1, color) +
            path(x1d, y0-t, x11, y0, x1d, y0+t, color=color)
        )

    def rect(x, y, w, h, ry, color, stroke_width : "int|None" = stroke_width, border_color="#000000"):

        return svg_tag("rect",
            width=w,
            height=h,
            x=x, y=y, ry=ry,
            style={
                **themed_color("fill", color),
                **({
                    **themed_color("stroke", border_color),
                    "stroke-width":f"{stroke_width}px",
                } if stroke_width is not None else {})
            }
        )()


    def actor_left(i):
        #return i*(actor_width+msg_width)
        return sum((or_default(a.width, actor_width)) + or_default(a.message_space_right, msg_width) for a in actors[:i])
    
    def actor_right(i):
        #return actor_left(i)+actor_width
        return actor_left(i) + or_default(actors[i].width, actor_width)

    def actor_center(i):
        return (actor_left(i)+actor_right(i))/2

    for i, actor in enumerate(actors):
        if actor.display_text:
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

            y = cursor+msg_height*0.5
            draw_elements += arrow(sx, y, dx, y, line_color)
            if e.msg:
                text_elements += text((sx+dx)/2, y-msg_txtup,
                    adjust="center", 
                    color=line_color,
                    text=e.msg)#f"{{\\footnotesize {e.msg}}}")

        elif isinstance(e, Action):
            action = e.action

            is_line = len(action) >= 3 and action.strip("-") == "" # action == "-"*len(action)

            e_line_height = e.line_height
            if e_line_height is None: e_line_height = 0.25 if is_line else 1

            cursor = actor_cursors[e.actor]
            actor_cursors[e.actor] = cursor + e_line_height*line_height

            if is_line:
                # TODO: better
                y = cursor+0.5*e_line_height*line_height + line_height*0.3
                draw_elements += line(actor_left(e.actor)+leftpad, y, actor_right(e.actor)-leftpad, y, actor.fg_color)
            elif action:
                y = cursor+(0.5+e_line_height*0.5)*line_height
                bold = False
                italic = False

                def parse_whole_bi(s, n):
                    s=s.strip()
                    if s.startswith("*"*n):
                        return s[n:].rstrip("*")
                    if s.startswith("_"*n):
                        return s[n:].rstrip("_")

                center = False
                if action[:1] == action[-1:] == '??':
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
        if actor.box_visible:
            lt = actor_left(i)
            wd = or_default(actor.width, actor_width)
            pd = 3
            outer_rect = (lt, 0, wd, svgh)
            inner_rect = (lt+pd, pd, wd-2*pd, svgh-2*pd)

            if actor.hl_color is not None:
                rect_elements += rect(*outer_rect, rect_ry, actor.hl_color, border_color=line_color)
                rect_elements += rect(*inner_rect, rect_ry-pd, actor.bg_color, None)
            else:
                rect_elements += rect(*outer_rect, rect_ry, actor.bg_color, border_color=line_color)
            if actor.title_line:
                y = 30
                rect_elements += line(lt+leftpad, y, lt+wd-leftpad, y, actor.fg_color)

    css_dark_styles = f"""@media (prefers-color-scheme:dark) {{\n{css_dark_styles}}}\n"""
    style = f"""<style>\n{css_light_styles}{css_dark_styles}</style>\n"""

    svg = style + rect_elements + draw_elements + text_elements

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
