"""
I certify that no unauthorized assistance has been received or given in the completion of this work
Signed: Oliver Chen
Date: February 21, 2023
"""

import sys
import os
from enum import Enum
from socket import *

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
- [ ] **TCP socket**
"""

do_debug = False


def debug(message: str):
    global do_debug
    if do_debug:
        sys.stderr.write(f"{message}" + "\n" if message[-1] != "\n" else "")


class ResponseParser:
    def __init__(self, message: str):
        self.stream = iter(message)
        self.next = next(self.stream)

    def put_next(self):
        try:
            self.next = next(self.stream)
        except StopIteration:
            self.next = ""

    def consume(self, s: str):
        for c in s:
            if self.next != c:
                return False
            self.put_next()
        return True

    def parse_code(self) -> int:
        code = self.resp_number()
        if self.whitespace() and self.arbitrary() and self.crlf():
            return code
        return -1

    def resp_number(self):
        if self.consume("22"):
            if self.consume("0"):
                return 220
            return 221
        for num in ["250", "354"]:
            if self.consume(num):
                return int(num)
        if not self.consume("50"):
            return -1
        for num in ["0", "1", "3"]:
            if self.consume(num):
                return int("50" + num)

    def whitespace(self):
        if self.next not in (" ", "\t"):
            return False

        self.put_next()
        self.whitespace()
        return True

    def arbitrary(self):
        while self.next != "\n":
            self.put_next()

        return True

    def crlf(self):
        return self.next == "\n"


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
        HELO = -1
        FROM = 0
        TO = 1
        DATA = 2
        QUIT = 99
        ERROR = 100

    def __init__(self, hostname, port):
        self.state = self.State.HELO
        self.server = (hostname, port)
        try:
            self.cli_socket = socket(AF_INET, SOCK_STREAM)
            self.cli_socket.connect(self.server)
        except OSError:
            self.state = self.State.ERROR

    def send(self, cmd: str):
        self.cli_socket.send(cmd.encode())

    def main(self):
        msg_res = self.get_message()
        if msg_res is None:
            return
        from_, to, subj, msg = msg_res

        self.react_to_response(220, self.State.FROM)
        if self.state != self.State.QUIT:
            self.send(f"HELO cs.unc.edu\n")

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
                            self.send(f"RCPT TO: <{next(to_stream)}>\n")
                            self.react_to_response(250, self.State.TO)
                        except StopIteration:
                            self.state = self.State.DATA
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
        print(f"Encountered an SMTP error: '{msg}'")

    def react_to_response(self, expected_code: int, next_state: State = State.QUIT) -> bool:
        try:
            response, serv_addr = self.cli_socket.recv(1024)
        except OSError as e:
            print(f"Encountered a socket error: {e}")
            return False

        message = response.decode()
        code = ResponseParser(message).parse_code()

        if code != expected_code:
            # self.quit()
            self.error(message)
        else:
            self.state = next_state

        return True


def main():
    hostname = None  # server hostname
    port = -1  # server port
    if len(sys.argv) > 2:
        try:
            hostname = sys.argv[1]
            port = int(sys.argv[2])
        except IndexError:
            sys.stderr.write("Not enough arguments, expected hostname followed by port number\n")
        except ValueError:
            sys.stderr.write(f"Argument {sys.argv[2]} is not a valid port number\n")

    client = Client(hostname, port)
    client.main()


if __name__ == '__main__':
    main()
