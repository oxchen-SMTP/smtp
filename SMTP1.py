"""
I certify that no unauthorized assistance has been received or given in the completion of this work
Signed: Oliver Chen
Date: February 21, 2023
"""
import os
import re
import sys
from enum import Enum, auto
from socket import *
import logging

logging.basicConfig(format='%(level)s%(message)s', level=logging.DEBUG)

debug = False

"""
Checklist

- [x] Get port number from arguments
- [ ] Establish and accept a connection with the client
- [ ] Create a listening socket on the specified port number
- [ ] Handshake
    - Send a 220 code with text [server-hostname].cs.unc.edu
    - Receive and recognize a HELO command with text [client-hostname].cs.unc.edu
    - Send a 250 code with greeting text
- [ ] Begin receiving SMTP commands
- [ ] Upon QUIT command, respond to client with 221 [server-hostname] closing connection
- [ ] Close socket to client and await connection from another client
"""


class State(Enum):
    HELO = auto()
    MAIL = auto()
    RCPT = auto()
    RCPTDATA = auto()
    DATABODY = auto()
    QUIT = auto()


class Command(Enum):
    # TODO: decide whether to include pattern in Command
    def __init__(self, _: int, states: tuple[State], success_code: int, pattern: str):
        self.states = states
        self.success_code = success_code
        self.pattern = pattern

    HELO = auto(), State.HELO, 250, \
        r"^HELO\s(([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*))\n$"
    MAIL = auto(), State.MAIL, 250, \
        r"^MAIL\s+FROM:\s*<([^<>()[\]\\.,;:@\"]+)@(([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*))>\s*\n$"
    RCPT = auto(), (State.RCPT, State.RCPTDATA), 250, \
        r"^RCPT\s+TO:\s*<([^<>()[\]\\.,;:@\"]+)@(([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*))>\s*\n$"
    DATA = auto(), State.RCPTDATA, 354, r"^DATA\s*\n$"
    QUIT = auto(), State.QUIT, 221, r"^QUIT\s*\n"
    UNRECOGNIZED = auto(), tuple(State), -1, ""


class SMTPParser:
    SPECIAL = ("<", ">", "(", ")", "[", "]", "\\", ".", ",", ";", ":", "@", "\"")
    SP = (" ", "\t")
    ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    DIGIT = "0123456789"

    def __init__(self, connection_socket: socket):
        self.state = State.MAIL
        self.forward_path_strs = set()  # set of unique forward paths

        self.stream = iter([])  # iterator for stdin
        self.nextc = ""  # 1 character lookahead
        self.reverse_path_str = ""  # backward path
        self.get_reverse_path = False  # flag to insert to path_buffer

        self.get_forward_path = False  # flag to insert to path_buffer
        self.path_buffer = ""  # temporary buffer for forward paths
        self.data = ""  # temporary buffer for data
        self.data_buffer = ""  # temporary buffer for detecting end of data message
        self.reading_data = False  # flag activated while reading data
        self.valid_command = False

        self.conn_socket = connection_socket

    def main(self):
        # self.__init__()
        send(self.conn_socket, f"220 {gethostname()}")
        while self.state != State.QUIT:
            message = self.conn_socket.recv(1024).decode()
            # self.stream = iter(message)
            # self.putc()
            if self.state == State.DATABODY:
                # captures body in 0
                re_match = re.match(r"^(.*\n)\.\n$", message)
                if re_match:
                    send(self.code(250, "OK"))
                    body = re_match.group(0)
                    for fpath in self.forward_path_strs:
                        with open(os.path.join("./forward", fpath), "a+") as fp:
                            fp.write(body)
                    self.forward_path_strs = set()
                    self.state = State.MAIL
                else:
                    send(self.code(501))
                # res = self.read_data()
                # if res is not None:
                #     # found proper end of message
                #     if self.reading_data:
                #         print(self.code(501))
                #     else:
                #         fpath_to_strs = "\n".join([f"To: <{fpath}>" for fpath in self.forward_path_strs])
                #         for fpath in self.forward_path_strs:
                #             with open(f"./forward/{fpath}", "a+") as fp:
                #                 fp.write(f"From: <{self.reverse_path_str}>\n")
                #                 fp.write(fpath_to_strs + "\n")
                #                 fp.write(res + "\n")
                #         print(self.code(250))
                #         self.forward_path_strs = set()
                #         self.reverse_path_str = ""
                #         self.state = State.MAIL
            else:
                command = self.parse_cmd(message)
                if self.state not in command.states:
                    self.send(self.code(503))
                    self.state = State.MAIL
                else:
                    if command == Command.UNRECOGNIZED:
                        self.state = State.MAIL
                    else:
                        re_match = re.match(command.pattern, message)
                        if re_match:
                            match command:
                                case Command.HELO:
                                    # captures hostname/domain name in 0
                                    client_hostname = re_match.group(0)
                                    self.send(self.code(250, f"Hello {client_hostname} pleased to meet you"))
                                    self.state = State.MAIL
                                case Command.MAIL:
                                    # captures local-part in 0, domain name in 1
                                    self.send(self.code(250, f"OK"))
                                    self.forward_path_strs = set()
                                    self.state = State.RCPT
                                case Command.RCPT:
                                    # captures local-part in 0, domain name in 1
                                    self.send(self.code(250, f"OK"))
                                    domain = re_match.group(1)
                                    self.forward_path_strs.add(domain)
                                    self.state = State.RCPTDATA
                                case Command.DATA:
                                    self.send(self.code(354))
                                    self.state = State.DATABODY
                                case Command.QUIT:
                                    self.send(self.code(221))
                        else:
                            self.send(self.code(501))

                # command, states, exit_code = self.recognize_cmd()
                #
                # if self.state not in states:
                #     print(self.code(503))
                #     self.state = State.MAIL
                # else:
                #     match command:
                #         case "MAIL":
                #             self.forward_path_strs = []
                #             self.state = State.RCPT
                #         case "RCPT":
                #             self.state = State.RCPTDATA
                #         case "DATA":
                #             self.state = State.DATABODY
                #         case _:
                #             self.state = State.MAIL
                #     print(exit_code)

    def send(self, s: str):
        send(self.conn_socket, s)

    @staticmethod
    def parse_cmd(line: str) -> Command:
        # HELO
        if re.match(r"^HELO\s+", line):
            return Command.HELO

        # MAIL FROM
        if re.match(r"^MAIL\s+FROM:", line):
            return Command.MAIL

        # RCPT TO
        if re.match(r"^RCPT\s+TO:", line):
            return Command.RCPT

        # DATA
        if re.match(r"^DATA\s*"):
            return Command.DATA

        # QUIT
        if re.match(r"^QUIT\s*"):
            return Command.QUIT

        return Command.UNRECOGNIZED

    def parse_regex(self, command: Command, line: str) -> re.Match:
        return re.match(command.pattern, line)

    def putc(self):
        if self.get_forward_path or self.get_reverse_path:
            self.path_buffer += self.nextc
        try:
            self.nextc = next(self.stream)
        except StopIteration:
            self.nextc = ""

    @staticmethod
    def code(num: int, data: str = "") -> str:
        match num:
            case 220:
                return f"220 {gethostname()}"
            case 221:
                return f"221 {gethostname()} closing connection"
            case 250:
                return f"250 {data}"
            case 354:
                return "354 Start mail input; end with <CRLF>.<CRLF>"
            case 500:
                return "500 Syntax error: command unrecognized"
            case 501:
                return "501 Syntax error in parameters or arguments"
            case 503:
                return "503 Bad sequence of commands"

    @staticmethod
    def error(token: str) -> str:
        if debug:
            print(f"error while parsing {token=}")
        return f"ERROR -- {token}"

    def read_data(self):
        self.reading_data = True
        while self.data_buffer != "\n.\n":
            valid_crlf = self.nextc == "\n" and (len(self.data_buffer) in [0, 2])
            valid_period = self.nextc == "." and len(self.data_buffer) == 1
            if valid_crlf or valid_period:
                self.data_buffer += self.nextc
                self.putc()
            elif self.nextc == "":
                # reached end of line
                return None
            else:
                # invalid ending seen, add buffer to data and clear it
                self.data += self.data_buffer
                self.data_buffer = ""
                # after clearing the buffer, insert the next char
                self.data += self.nextc
                self.putc()
        # buffer was correct ending, so reset buffer and return data
        self.data_buffer = ""
        out = self.data
        self.data = ""  # ensure data line is cleared before next data is read
        self.reading_data = False
        return out

    def consume_str(self, s: str) -> bool:
        for c in s:
            if self.nextc != c:
                if debug:
                    print(f"searching for '{c}', found '{self.nextc}'")
                return False
            self.putc()
        if debug:
            print(f"found string {s}")
        return True

    def recognize_cmd(self) -> (list, str):  # returns tuple of (command, exit code)
        if self.consume_str("MAIL") and not self.whitespace() and self.consume_str("FROM:"):
            return "MAIL", [State.MAIL], self.mail_from_cmd()

        if self.consume_str("RCPT") and not self.whitespace() and self.consume_str("TO:"):
            return "RCPT", [State.RCPT, State.RCPTDATA], self.rcpt_to_cmd()

        if self.consume_str("DATA") and not self.nullspace() and not self.crlf():
            return "DATA", [State.RCPTDATA], self.data_cmd()

        return "UNRECOGNIZED", [State.MAIL, State.RCPT, State.RCPTDATA], self.code(500)

    def mail_from_cmd(self):
        # <mail-from-cmd> ::= "MAIL" <whitespace> "FROM:" <nullspace> <reverse-path> <nullspace> <CRLF>
        # already recognized command

        if self.nullspace() or self.reverse_path() or self.nullspace() or self.crlf():
            return self.code(501)

        return self.code(250)

    def whitespace(self):
        # <whitespace> ::= <SP> | <SP> <whitespace>
        if self.sp() != "":
            return self.error("whitespace")

        self.whitespace()

        return ""

    def sp(self):
        # <SP> ::= the space or tab character
        if self.nextc in self.SP:
            self.putc()
            return ""
        return self.error("sp")

    def nullspace(self):
        # <nullspace> ::= <null> | <whitespace>
        self.whitespace()
        return ""

    def reverse_path(self):
        # <reverse-path> ::= <path>
        self.path_buffer = ""
        self.get_reverse_path = True
        return self.path()

    def path(self):
        # <path> ::= "<" <mailbox> ">"
        if not self.consume_str("<"):
            return self.error("path")

        res = self.mailbox()
        if res != "":
            return res

        if not self.consume_str(">"):
            return self.error("path")

        return ""

    def mailbox(self):
        # <mailbox> ::= <local-part> "@" <domain>
        res = self.local_part()
        if res != "":
            return res

        if not self.consume_str("@"):
            return self.error("mailbox")

        res = self.domain()
        if res != "":
            return res

        if self.get_forward_path:
            self.forward_path_strs.append(self.path_buffer.strip("<>"))
            self.path_buffer = ""
            self.get_forward_path = False
        if self.get_reverse_path:
            self.reverse_path_str = self.path_buffer.strip("<>")
            self.path_buffer = ""
            self.get_reverse_path = False
        return ""

    def local_part(self):
        # <local-part> ::= <string>
        return self.string()

    def string(self):
        # <string> ::= <char> | <char> <string>
        res = self.char()
        if res != "":
            return self.error("string")

        self.string()

        return ""

    def char(self):
        # <char> ::= any one of the printable ASCII characters, but not any of <special> or <SP>
        if self.nextc in self.SPECIAL or self.nextc in self.SP:
            return self.error("char")
        self.putc()
        return ""

    def domain(self):
        # <domain> ::= <element> | <element> "." <domain>
        res = self.element()
        if res != "":
            return res

        if self.nextc == ".":
            self.consume_str(".")
            return self.domain()  # this element is fine, next one also needs to be

        return ""

    def element(self):
        # <element> ::= <letter> | <name>
        if self.letter() != "":
            return self.error("element")

        self.name()

        return ""

    def name(self):
        # <name> ::= <letter> <let-dig-str>
        if self.let_dig_str():
            return self.error("name")

        return ""

    def letter(self):
        # <letter> ::= any one of the 52 alphabetic characters A through Z in upper case and a through z in lower case
        if self.nextc in self.ALPHA:
            self.putc()
            return ""
        return self.error("letter")

    def let_dig_str(self):
        # <let-dig-str> ::= <let-dig> | <let-dig> <let-dig-str>
        if self.let_dig() != "":
            return self.error("let-dig-str")

        self.let_dig_str()

        return ""

    def let_dig(self):
        # <let-dig> ::= <letter> | <digit>
        if self.letter() != "" and self.digit() != "":
            return self.error("let-dig")
        return ""

    def digit(self):
        # <digit> ::= any one of the ten digits 0 through 9
        if self.nextc in self.DIGIT:
            self.putc()
            return ""
        return self.error("digit")

    def crlf(self):
        # <CRLF> ::= the newline character
        if not self.consume_str("\n"):
            return self.error("CRLF")
        return ""

    def special(self):
        # <special> ::= "<" | ">" | "(" | ")" | "[" | "]" | "\" | "." | "," | ";" | ":" | "@" | """
        if self.nextc in self.SPECIAL:
            self.putc()
            return ""
        return self.error("special")

    def rcpt_to_cmd(self):
        # <rcpt-to-cmd> ::= ["RCPT"] <whitespace> "TO:" <nullspace> <forward-path> <nullspace> <CRLF>
        # Already recognized command

        if self.nullspace() or self.forward_path() or self.nullspace() or self.crlf():
            return self.code(501)

        return self.code(250)

    def forward_path(self):
        # <forward-path> ::= <path>
        self.path_buffer = ""
        self.get_forward_path = True
        return self.path()

    def data_cmd(self):
        # <data-cmd> ::= "DATA" <nullspace> <CRLF>
        return self.code(354)


def send(sock: socket, s: str):
    sock.send(f"{s}\n".encode())


def main():
    port = -1
    # TODO: proper behavior if invalid port number
    # TODO: proper behavior if non-protocol error
    try:
        port = int(sys.argv[1])
    except IndexError:
        logging.debug("No port number given\n")
    except ValueError:
        logging.debug(f"Argument {sys.argv[1]} is not a valid port number\n")

    with socket(AF_INET, SOCK_DGRAM) as serv_socket:
        serv_socket.bind(("", port))
        serv_socket.listen(1)

        while True:
            with serv_socket.accept() as (conn_socket, addr):
                logging.debug("accepted connection, handshaking")
                # conn_socket listens to cli_socket
                try:
                    parser = SMTPParser(conn_socket)
                    parser.main()
                except OSError as e:
                    print(f"Encountered a socket error: {e}")
                except Exception as e:
                    print("Encountered an exception: {e}")



if __name__ == "__main__":
    main()
