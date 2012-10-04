import re
from abc import ABCMeta, abstractmethod
from ccformat import CCFormatter

non_alphabets_re = re.compile('[^a-zA-Z0-9_]')

class Writer(metaclass=ABCMeta):
    """
    A generic C++ file writer.
    """

    def __init__(self, filename):
        self._filename = filename
        self._writer = CCFormatter()

    def __enter__(self):
        self.write_prolog()
        return self

    def __exit__(self, p, q, r):
        self.write_epilog()
        with open(self._filename, 'w') as f:
            f.writelines(self._writer.lines)
        return False

    def write(self, code):
        """
        Write a piece of C++ code to this file.
        """
        self._writer.write(code)

    @property
    def filename(self):
        """
        Return the file name associated to this writer.
        """
        return self._filename

    @abstractmethod
    def write_prolog(self):
        """
        Write the prolog of the file. In this function, you usually add #include
        guards, include headers and namespaces.

        The default implementation just writes the #include guard.
        """
        guard = 'M2G3_' + non_alphabets_re.sub('_', self._filename).upper()
        self.write("#ifndef " + guard)
        self.write("#define " + guard)

    @abstractmethod
    def write_epilog(self):
        """
        Write the epilog of the file. In this function, you usually close the
        namespaces and include guards defined in write_prolog().

        The default implementation just closes the #include guard.
        """
        self.write("#endif")

