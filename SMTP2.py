"""
I certify that no unauthorized assistance has been received or given in the completion of this work
Signed: Oliver Chen
Date: February 21, 2023
"""

import sys
import os
from enum import Enum, auto
from socket import *
import re
import logging

# logging.basicConfig(filename='example.log', encoding='utf-8', level=logging.DEBUG)
logging.basicConfig(format='%(message)s', level=logging.INFO)

"""
Checklist:

- [x] Take hostname and port number from command line arguments
- [x] Prompt and receive email information from the user through the message
- [x] Create a TCP socket to the SMTP server at the host and port number
- [x] Handshake
    - Receive and recognize a 220 code and confirm it's valid
    - Reply with an SMTP HELO message (HELO <whitespace> <domain> <nullspace> <CRLF>)
    - (Receive and reconize a 250 code)
- [x] Format the message data from the user and send it to the server
- [x] Receive and recognize a 221 code after quitting
- [x] **TCP socket**
"""

do_debug = False


def debug(message: str):
    global do_debug
    if do_debug:
        sys.stderr.write(f"{message}" + "\n" if message[-1] != "\n" else "")


class PathParser:
    SPECIAL = ("<", ">", "(", ")", "[", "]", "\\", ".", ",", ";", ":", "@", "\"")
    SP = (" ", "\t")
    ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    DIGIT = "0123456789"

    def __init__(self, path: str):
        self.stream = iter(path)
        self.nextc = next(self.stream)

    def parse_path(self) -> str:
        if self.local_part() != "":
            return "Invalid local name"

        if not self.consume("@"):
            return "Missing @ in path"

        if self.domain() != "":
            return "Invalid domain name"

        return ""

    def putc(self):
        try:
            self.nextc = next(self.stream)
        except StopIteration:
            self.nextc = ""

    def consume(self, s: str):
        for c in s:
            if self.nextc != c:
                return False
            self.putc()
        return True

    def local_part(self):
        # <local-part> ::= <string>
        return self.string()

    def string(self):
        # <string> ::= <char> | <char> <string>
        res = self.char()
        if res != "":
            return "string"

        self.string()

        return ""

    def char(self):
        # <char> ::= any one of the printable ASCII characters, but not any of <special> or <SP>
        if self.nextc in self.SPECIAL or self.nextc in self.SP:
            return "char"
        self.putc()
        return ""

    def domain(self):
        # <domain> ::= <element> | <element> "." <domain>
        res = self.element()
        if res != "":
            return res

        if self.nextc == ".":
            self.consume(".")
            return self.domain()  # this element is fine, next one also needs to be

        return ""

    def element(self):
        # <element> ::= <letter> | <name>
        if self.letter() != "":
            return "element"

        self.name()

        return ""

    def name(self):
        # <name> ::= <letter> <let-dig-str>
        if self.let_dig_str():
            return "name"

        return ""

    def letter(self):
        # <letter> ::= any one of the 52 alphabetic characters A through Z in upper case and a through z in lower case
        if self.nextc in self.ALPHA:
            self.putc()
            return ""
        return "letter"

    def let_dig_str(self):
        # <let-dig-str> ::= <let-dig> | <let-dig> <let-dig-str>
        if self.let_dig() != "":
            return "let-dig-str"

        if self.nextc == "":
            return ""

        self.let_dig_str()

        return ""

    def let_dig(self):
        # <let-dig> ::= <letter> | <digit>
        if self.letter() != "" and self.digit() != "":
            return "let-dig"
        return ""

    def digit(self):
        # <digit> ::= any one of the ten digits 0 through 9
        if self.nextc in self.DIGIT:
            self.putc()
            return ""
        return "digit"


class Client:
    class State(Enum):
        HELO = auto()
        FROM = auto()
        TO = auto()
        DATA = auto()
        QUIT = auto()
        ERROR = auto()

    def __init__(self, hostname, port):
        self.state = self.State.HELO
        self.server = (hostname, port)
        try:
            self.cli_socket = socket(AF_INET, SOCK_STREAM)
            self.cli_socket.connect(self.server)
            logging.debug(f"connected to {hostname}")
        except OSError:
            self.state = self.State.ERROR
        finally:
            self.cli_socket.close()

    def send(self, s: str):
        self.cli_socket.send(s.encode())

    def main(self):
        if self.state == self.state.ERROR:
            self.cli_socket.close()
            return

        msg_res = self.get_message()
        if msg_res is None:
            self.cli_socket.close()
            return
        from_, to, subj, msg = msg_res

        self.react_to_response(220, self.State.FROM)
        if self.state not in [self.State.QUIT, self.State.ERROR]:
            self.send(f"HELO {gethostname()}\n")

        to_stream = iter(to)
        while True:
            # TODO: review SMTP and socket error handling + connection closing
            try:
                match self.state:
                    case self.State.FROM:
                        # command MAIL FROM:
                        self.send(f"MAIL FROM: <{from_}>\n")
                        self.react_to_response(250, self.State.TO)
                    case self.State.TO:
                        # command(s) RCPT TO:
                        try:
                            n = next(to_stream)
                            logging.debug(n)
                            self.send(f"RCPT TO: <{next(to_stream)}>\n")
                            self.react_to_response(250, self.State.TO)
                        except StopIteration:
                            self.react_to_response(250, self.State.DATA)
                    case self.State.DATA:
                        # command DATA + message
                        self.send("DATA\n")
                        self.react_to_response(354, self.State.DATA)
                        self.send(f"From: <{from_}>\n"
                                  f"To: {', '.join([f'<{path}>' for path in to])}\n"
                                  f"Subject: {subj}\n\n"
                                  f"{msg}\n"
                                  f".\n"
                                  )
                        self.react_to_response(250)
                    case self.State.QUIT:
                        self.send("QUIT\n")
                        self.react_to_response(221)
                        break
                    case self.State.ERROR:
                        break
            except OSError as e:
                print(f"Encountered a socket error: '{e}'")
                break

        self.cli_socket.close()

    @staticmethod
    def get_message() -> (str, list[str], str, str):
        try:
            # Prompt From:
            from_ = None
            while from_ is None:
                path = input("From:\n")
                res = PathParser(path).parse_path()
                if res != "":
                    print(res)
                else:
                    from_ = path

            # Prompt To:
            to = None
            while to is None:
                paths = input("To:\n").split(", \t")
                for p in paths:
                    res = PathParser(p).parse_path()
                    if res != "":
                        print(res)
                        continue
                to = paths

            # Prompt Subject:
            subj = input("Subject:\n")

            # Prompt Message:
            print("Message:")
            msg = ""
            line = ""
            while line != ".":
                msg += line
                line = input("")

            return from_, to, subj, msg
        except EOFError:
            return None

    def quit(self):
        # self.send("QUIT\n")
        self.state = self.State.QUIT

    @staticmethod
    def error(msg: str):
        # TODO: handle SMTP error
        print(f"Encountered an SMTP error: {repr(msg)}")

    @staticmethod
    def parse_code(message: str) -> int:
        match = re.match(r"^(\d{3})\s+.*\n$", message)
        if not match:
            return -1
        return int(match.group(1))

    def react_to_response(self, expected_code: int, next_state: State = State.QUIT) -> bool:
        try:
            response = self.cli_socket.recv(1024)
        except OSError as e:
            print(f"Encountered a socket error: {e}")
            return False

        message = response.decode()
        code = self.parse_code(message)
        logging.debug(f"{self.state}")
        logging.debug(f"{expected_code=}, {code=}, {next_state=}")

        if code != expected_code:
            self.error(message)
        else:
            self.state = next_state

        return True


def main():
    hostname = None  # server hostname
    port = -1  # server port
    if len(sys.argv) > 2:
        # TODO: how to handle bad arguments
        try:
            hostname = sys.argv[1]
            port = int(sys.argv[2])
        except IndexError:
            logging.debug("Not enough arguments, expected hostname followed by port number\n")
        except ValueError:
            logging.debug(f"Argument {sys.argv[2]} is not a valid port number\n")

        client = Client(hostname, port)
        client.main()


if __name__ == '__main__':
    main()
