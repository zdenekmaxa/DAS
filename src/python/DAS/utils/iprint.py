#!/usr/bin/env python
#-*- coding: ISO-8859-1 -*-

"""
Print utilities
"""

__revision__ = "$Id: iprint.py,v 1.1 2009/06/10 20:33:03 valya Exp $"
__version__ = "$Revision: 1.1 $"
__author__ = "Valentin Kuznetsov"

import sys
import re
import time

class PrintManager:
    def __init__(self):
        self.term = TerminalController()

    def print_red(self, msg):
        """print message using red color"""
        print self.msg_red(msg)

    def print_green(self, msg):
        """print message using blue color"""
        print self.msg_green(msg)

    def print_blue(self, msg):
        """print message using blue color"""
        print self.msg_blue(msg)

    def msg_red(self, msg):
        """yield message using red color"""
        return self.term.red + msg + self.term.NORMAL

    def msg_green(self, msg):
        """yield message using green color"""
        return self.term.green + msg + self.term.NORMAL

    def msg_blue(self, msg):
        """yield message using blue color"""
        return self.term.BLUE + msg + self.term.NORMAL

    def print_txt(self, tlist, olist, llist, msg=None):
        """
        Print text in a form of table
        --------------
        title1  title2
        --------------
        val     value
        """
        s = ""
        for item in llist:
            s += "-"*(item+2) # add 2 char space for wrap
        print s
        for idx in xrange(0, len(tlist)):
            title  = tlist[idx]
            length = llist[idx]
            print "%s%s " %(title, " "*abs(length-len(title))),
        print
        print s
        for item in olist:
            for idx in xrange(0, len(item)):
                elem = str(item[idx])
                length = llist[idx]
                print "%s%s " % (elem, " "*abs(length-len(elem))),
            print
        print s

    def print_xml(self, tlist, olist, llist, msg=None):
        """Print in XML format"""
        s  = """<?xml version="1.0" encoding="utf-8"?>\n"""
        s += "<query>\n"
        s += "  <sql>%s</sql>\n" % msg
        s += "  <table>\n"
        for item in olist:
            s += "    <row>\n"
            for idx in xrange(0,len(item)):
                t  = item[idx]
                s +="      <%s>%s</%s>\n" %(tlist[idx], t, tlist[idx])
            s += "    </row>\n"
        s += "  </table>\n"
        s += "</query>\n"
        print s

    def print_html(self, tlist, olist, llist, msg=None):
        """Print in HTML format"""
        s  = "<table class=\"dbsh_table\">\n"
        s += "<th>\n"
        for t in tlist:
            s += "<td>%s</td>\n" % t
        s += "</th>\n"
        for item in olist:
            s += "<tr>\n"
            for t in item:
                s += "<td>%s</td>\n" % t
            s += "</tr>\n"
        s += "</table>\n"
        print s

    def print_cvs(self, tlist, olist, llist, msg=None):
        """Print in CVS format"""
        for t in tlist:
            if  t != tlist[:-1]:
                print "%s," % t,
            else:
                print t
        print
        for item in olist:
            for o in item:
                if  o != olist[:-1]:
                    print "%s,"%o,
                else:
                    print o

#
# http://code.activestate.com/recipes/475116/
#
class TerminalController:
    """
    A class that can be used to portably generate formatted output to
    a terminal.  
    
    `TerminalController` defines a set of instance variables whose
    values are initialized to the control sequence necessary to
    perform a given action.  These can be simply included in normal
    output to the terminal:

        >>> term = TerminalController()
        >>> print 'This is '+term.GREEN+'green'+term.NORMAL

    Alternatively, the `render()` method can used, which replaces
    '${action}' with the string required to perform 'action':

        >>> term = TerminalController()
        >>> print term.render('This is ${GREEN}green${NORMAL}')

    If the terminal doesn't support a given action, then the value of
    the corresponding instance variable will be set to ''.  As a
    result, the above code will still work on terminals that do not
    support color, except that their output will not be colored.
    Also, this means that you can test whether the terminal supports a
    given action by simply testing the truth value of the
    corresponding instance variable:

        >>> term = TerminalController()
        >>> if term.CLEAR_SCREEN:
        ...     print 'This terminal supports clearning the screen.'

    Finally, if the width and height of the terminal are known, then
    they will be stored in the `COLS` and `LINES` attributes.
    """
    # Cursor movement:
    BOL = ''             #: Move the cursor to the beginning of the line
    UP = ''              #: Move the cursor up one line
    DOWN = ''            #: Move the cursor down one line
    LEFT = ''            #: Move the cursor left one char
    RIGHT = ''           #: Move the cursor right one char

    # Deletion:
    CLEAR_SCREEN = ''    #: Clear the screen and move to home position
    CLEAR_EOL = ''       #: Clear to the end of the line.
    CLEAR_BOL = ''       #: Clear to the beginning of the line.
    CLEAR_EOS = ''       #: Clear to the end of the screen

    # Output modes:
    BOLD = ''            #: Turn on bold mode
    BLINK = ''           #: Turn on blink mode
    DIM = ''             #: Turn on half-bright mode
    REVERSE = ''         #: Turn on reverse-video mode
    NORMAL = ''          #: Turn off all modes

    # Cursor display:
    HIDE_CURSOR = ''     #: Make the cursor invisible
    SHOW_CURSOR = ''     #: Make the cursor visible

    # Terminal size:
    COLS = None          #: Width of the terminal (None for unknown)
    LINES = None         #: Height of the terminal (None for unknown)

    # Foreground colors:
    BLACK = BLUE = GREEN = CYAN = RED = MAGENTA = YELLOW = WHITE = ''
    
    # Background colors:
    BG_BLACK = BG_BLUE = BG_GREEN = BG_CYAN = ''
    BG_RED = BG_MAGENTA = BG_YELLOW = BG_WHITE = ''
    
    _STRING_CAPABILITIES = """
    BOL=cr UP=cuu1 DOWN=cud1 LEFT=cub1 RIGHT=cuf1
    CLEAR_SCREEN=clear CLEAR_EOL=el CLEAR_BOL=el1 CLEAR_EOS=ed BOLD=bold
    BLINK=blink DIM=dim REVERSE=rev UNDERLINE=smul NORMAL=sgr0
    HIDE_CURSOR=cinvis SHOW_CURSOR=cnorm""".split()
    _COLORS = """BLACK BLUE GREEN CYAN RED MAGENTA YELLOW WHITE""".split()
    _ANSICOLORS = "BLACK RED GREEN YELLOW BLUE MAGENTA CYAN WHITE".split()

    def __init__(self, term_stream=sys.stdout):
        """
        Create a `TerminalController` and initialize its attributes
        with appropriate values for the current terminal.
        `term_stream` is the stream that will be used for terminal
        output; if this stream is not a tty, then the terminal is
        assumed to be a dumb terminal (i.e., have no capabilities).
        """
        # Curses isn't available on all platforms
        try: import curses
        except: return

        # If the stream isn't a tty, then assume it has no capabilities.
        if not term_stream.isatty(): return

        # Check the terminal type.  If we fail, then assume that the
        # terminal has no capabilities.
        try: curses.setupterm()
        except: return

        # Look up numeric capabilities.
        self.COLS = curses.tigetnum('cols')
        self.LINES = curses.tigetnum('lines')
        
        # Look up string capabilities.
        for capability in self._STRING_CAPABILITIES:
            (attrib, cap_name) = capability.split('=')
            setattr(self, attrib, self._tigetstr(cap_name) or '')

        # Colors
        set_fg = self._tigetstr('setf')
        if set_fg:
            for i,color in zip(range(len(self._COLORS)), self._COLORS):
                setattr(self, color, curses.tparm(set_fg, i) or '')
        set_fg_ansi = self._tigetstr('setaf')
        if set_fg_ansi:
            for i,color in zip(range(len(self._ANSICOLORS)), self._ANSICOLORS):
                setattr(self, color, curses.tparm(set_fg_ansi, i) or '')
        set_bg = self._tigetstr('setb')
        if set_bg:
            for i,color in zip(range(len(self._COLORS)), self._COLORS):
                setattr(self, 'BG_'+color, curses.tparm(set_bg, i) or '')
        set_bg_ansi = self._tigetstr('setab')
        if set_bg_ansi:
            for i,color in zip(range(len(self._ANSICOLORS)), self._ANSICOLORS):
                setattr(self, 'BG_'+color, curses.tparm(set_bg_ansi, i) or '')

    def _tigetstr(self, cap_name):
        # String capabilities can include "delays" of the form "$<2>".
        # For any modern terminal, we should be able to just ignore
        # these, so strip them out.
        import curses
        cap = curses.tigetstr(cap_name) or ''
        return re.sub(r'\$<\d+>[/*]?', '', cap)

    def render(self, template):
        """
        Replace each $-substitutions in the given template string with
        the corresponding terminal control string (if it's defined) or
        '' (if it's not).
        """
        return re.sub(r'\$\$|\${\w+}', self._render_sub, template)

    def _render_sub(self, match):
        s = match.group()
        if s == '$$': return s
        else: return getattr(self, s[2:-1])

#######################################################################
# Example use case: progress bar
#######################################################################

class ProgressBar:
    """
    A 3-line progress bar, which looks like::
    
                                Header
        20% [===========----------------------------------]
                           progress message

    The progress bar is colored, if the terminal supports color
    output; and adjusts to the width of the terminal.
    """
    BAR = '%3d%% ${GREEN}[${BOLD}%s%s${NORMAL}${GREEN}]${NORMAL}\n'
    HEADER = '${BOLD}${CYAN}%s${NORMAL}\n\n'
        
    def __init__(self, term, header):
        self.term = term
        if not (self.term.CLEAR_EOL and self.term.UP and self.term.BOL):
            raise ValueError("Terminal isn't capable enough -- you "
                             "should use a simpler progress dispaly.")
        self.width = self.term.COLS or 75
        self.bar = term.render(self.BAR)
        self.header = self.term.render(self.HEADER % header.center(self.width))
        self.cleared = 1 #: true if we haven't drawn the bar yet.
        self.update(0, '')

    def update(self, percent, message):
        if self.cleared:
            sys.stdout.write(self.header)
            self.cleared = 0
        n = int((self.width-10)*percent)
        sys.stdout.write(
            self.term.BOL + self.term.UP + self.term.CLEAR_EOL +
            (self.bar % (100*percent, '='*n, '-'*(self.width-10-n))) +
            self.term.CLEAR_EOL + message.center(self.width))

    def clear(self):
        if not self.cleared:
            sys.stdout.write(self.term.BOL + self.term.CLEAR_EOL +
                             self.term.UP + self.term.CLEAR_EOL +
                             self.term.UP + self.term.CLEAR_EOL)
            self.cleared = 1

if __name__ == "__main__":

	term = TerminalController()
	print 'This is '+term.RED+'green'+term.NORMAL

	mypb = ProgressBar(term, "Test progress")
	#mypb.update(0.1, "doing...")
	for i in range(1, 10):
		mypb.update(i, "doing...")