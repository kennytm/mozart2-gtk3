from textwrap import dedent

class CCFormatter:
    """
    A class to format C++ source code. For now, it will only fix indentation of
    code by counting '{' and '}'s.
    """

    def __init__(self):
        self._lines = []
        self._indent = ""

    def write(self, lines):
        """
        Prettify the C++ source code in the input string, and then append it to
        the formatter.
        """
        strip_lines = lines.strip()
        if strip_lines:
            for line in strip_lines.split('\n'):
                self._add(line.strip())

    def _add(self, line):
        if not line:
            self._lines.append('\n')
            return
        open_braces = sum(1 for c in line if c in '{[(')
        close_braces = sum(1 for c in line if c in ')]}')
        indent_string = self._indent
        if line[0] == '}':
            indent_string = indent_string[4:]
        if close_braces > open_braces:
            self._indent = self._indent[4:]
        self._lines.extend((indent_string, line, '\n'))
        if open_braces > close_braces:
            self._indent += "    "

    def __str__(self):
        """
        Extract the content of the formatter as a string.
        """
        result = "".join(self._lines)
        self._lines = [result]
        return result

    @property
    def lines(self):
        """
        Extract the content of the formatter as an iterable of strings. The
        iterable can be concatenated.
        """
        return self._lines

