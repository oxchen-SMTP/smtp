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

logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)

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
    def __init__(self, _: int, states: tuple[State], success_code: int, pattern: str):
        self.states = states
        self.success_code = success_code
        self.pattern = pattern

    HELO = auto(), (State.HELO, ), 250, \
        r"^HELO\s(([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*))\n$"
    MAIL = auto(), (State.MAIL, ), 250, \
        r"^MAIL\s+FROM:\s*<([^<>()[\]\\.,;:@\"]+)@(([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*))>\s*\n$"
    RCPT = auto(), (State.RCPT, State.RCPTDATA), 250, \
        r"^RCPT\s+TO:\s*<([^<>()[\]\\.,;:@\"]+)@(([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*))>\s*\n$"
    DATA = auto(), (State.RCPTDATA, ), 354, r"^DATA\s*\n$"
    QUIT = auto(), (State.QUIT, ), 221, r"^QUIT\s*\n"
    UNRECOGNIZED = auto(), tuple(State), -1, ""


def send(sock: socket, s: str):
    sock.send(f"{s}\n".encode())


class SMTPParser:
    SPECIAL = ("<", ">", "(", ")", "[", "]", "\\", ".", ",", ";", ":", "@", "\"")
    SP = (" ", "\t")
    ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    DIGIT = "0123456789"

    def __init__(self, connection_socket: socket):
        self.state = State.MAIL
        self.forward_path_strs = set()  # set of unique forward paths
        self.conn_socket = connection_socket

    def main(self):
        self.send(f"220 {gethostname()}")
        while self.state != State.QUIT:
            message = self.conn_socket.recv(1024).decode()
            if self.state == State.DATABODY:
                # captures body in 0
                re_match = re.match(r"^(.*\n)\.\n$", message)
                if re_match:
                    self.send(self.code(250, "OK"))
                    body = re_match.group(0)
                    for fpath in self.forward_path_strs:
                        with open(os.path.join("./forward", fpath), "a+") as fp:
                            fp.write(body)
                    self.forward_path_strs = set()
                    self.state = State.MAIL
                else:
                    self.send(self.code(501))
            else:
                command = self.parse_cmd(message)
                logging.debug(command)
                if self.state not in command.states:
                    self.send(self.code(503))
                    self.state = State.MAIL
                else:
                    if command == Command.UNRECOGNIZED:
                        self.send(self.code(500))
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
                                    self.state = State.QUIT
                        else:
                            self.send(self.code(501))

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
        if re.match(r"^DATA\s*", line):
            return Command.DATA

        # QUIT
        if re.match(r"^QUIT\s*", line):
            return Command.QUIT

        return Command.UNRECOGNIZED

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

    with socket(AF_INET, SOCK_STREAM) as serv_socket:
        serv_socket.bind(("", port))
        serv_socket.listen(1)
        logging.debug(f"created server socket on port {port}")

        while True:
            try:
                conn_socket, addr = serv_socket.accept()
                logging.debug("accepted connection, handshaking")
                # conn_socket listens to cli_socket
                parser = SMTPParser(conn_socket)
                parser.main()
            except OSError as e:
                print(f"Encountered a socket error: {e}")
            # except Exception as e:
            #     print(f"Encountered an exception: {e}")
            finally:
                conn_socket.close()
                logging.debug("closed connection with client")

if __name__ == "__main__":
    main()
