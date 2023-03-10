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

# logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
logging.basicConfig(format="%(message)s", level=logging.INFO)


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

    HELO = auto(), (State.HELO,), 250, \
        r"^HELO\s+(([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*))\n$"
    MAIL = auto(), (State.MAIL,), 250, \
        r"^MAIL FROM:[\t ]*<([^<>()[\]\\.,;:@\"]+)@((?:(?:[a-zA-Z][a-zA-Z0-9]*)+\.)*(?:[a-zA-Z][a-zA-Z0-9]*)+)>[\t ]*\n$"
    RCPT = auto(), (State.RCPT, State.RCPTDATA), 250, \
        r"^RCPT TO:[\t ]*<([^<>()[\]\\.,;:@\"]+)@((?:(?:[a-zA-Z][a-zA-Z0-9]*)+\.)*(?:[a-zA-Z][a-zA-Z0-9]*)+)>[\t ]*\n$"
    DATA = auto(), (State.RCPTDATA,), 354, r"^DATA\s*\n$"
    QUIT = auto(), tuple(State), 221, r"^QUIT\s*\n"
    UNRECOGNIZED = auto(), tuple(State), -1, ""


def send(sock: socket, s: str):
    sock.send(f"{s}\n".encode())


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


class Server:
    SPECIAL = ("<", ">", "(", ")", "[", "]", "\\", ".", ",", ";", ":", "@", "\"")
    SP = (" ", "\t")
    ALPHA = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    DIGIT = "0123456789"

    def __init__(self, connection_socket: socket):
        self.state = State.HELO
        self.forward_path_strs = set()  # set of unique forward paths
        self.conn_socket = connection_socket
        self.command_buffer = []

    def main(self):
        try:
            self.send(f"220 {gethostname()}")
            while self.state != State.QUIT:
                logging.debug(f"{self.state=}")
                if not self.command_buffer:
                    recv = self.conn_socket.recv(1024).decode()
                    if recv.rstrip("\n") == "":
                        break
                    logging.debug(f"{recv=}".rstrip("\n"))
                    for m in re.findall("[^\n]*\n", recv):
                        self.command_buffer.append(m)
                        logging.debug(f"received: {m}".rstrip("\n"))
                if self.state == State.DATABODY:
                    self.interpret_body()
                else:
                    self.interpret_cmd()

            self.send(code(221))
        except OSError as e:
            print(f"Encountered a socket error during execution of the program: {e}")

    def send(self, s: str):
        logging.debug(f"sending: {s}".rstrip())
        send(self.conn_socket, s)

    def interpret_body(self):
        body = ""
        try:
            line = ""
            while line != "From:":
                body += line
                line = self.command_buffer.pop(0)
            body += line
        except IndexError:
            pass
        re_match = re.match(r"^((.*\n)*)\.\n", body)
        if not re_match:
            self.send(code(501))
            return
        self.send(code(250, "OK"))
        body = re_match.group(1)
        program_dir = os.path.abspath(os.path.dirname(__file__))
        forward_dir = os.path.join(program_dir, "forward")
        if not os.path.isdir(forward_dir):
            os.mkdir(forward_dir)
        for fpath in self.forward_path_strs:
            with open(os.path.join(forward_dir, fpath), "a+") as fp:
                logging.debug(f"writing {body} to ./forward/{fpath}")
                fp.write(body)
        self.forward_path_strs = set()
        self.state = State.MAIL

    def interpret_cmd(self):
        message = self.command_buffer.pop(0)
        command = parse_cmd(message)
        logging.debug(command)
        if self.state not in command.states:
            self.send(code(503))
            self.state = State.MAIL
            return
        if command == Command.UNRECOGNIZED:
            self.send(code(500))
            self.state = State.MAIL
            return
        re_match = re.match(command.pattern, message)
        if not re_match:
            self.send(code(501))
            return
        match command:
            case Command.HELO:
                # captures hostname/domain name in 1
                client_hostname = re_match.group(1)
                self.send(code(250, f"Hello {client_hostname} pleased to meet you"))
                self.state = State.MAIL
            case Command.MAIL:
                # captures local-part in 1, domain name in 2
                logging.debug(re_match.groups())
                self.send(code(250, f"mail from OK"))
                self.forward_path_strs = set()
                self.state = State.RCPT
            case Command.RCPT:
                # captures local-part in 1, domain name in 2
                logging.debug(re_match.groups())
                self.send(code(250, f"rcpt to OK"))
                domain = re_match.group(2)
                self.forward_path_strs.add(domain)
                self.state = State.RCPTDATA
            case Command.DATA:
                self.send(code(354))
                self.state = State.DATABODY
            case Command.QUIT:
                self.state = State.QUIT


def main():
    port = -1
    try:
        port = int(sys.argv[1])
    except IndexError:
        logging.debug("No port number given\n")
    except ValueError:
        logging.debug(f"Argument {sys.argv[1]} is not a valid port number\n")

    if port < 1 or port > 65536:
        logging.debug(f"Invalid port: {port}")
        return
    try:
        with socket(AF_INET, SOCK_STREAM) as serv_socket:
            serv_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            serv_socket.bind(("", port))
            serv_socket.listen(1)
            logging.debug(f"created server socket on port {port}")

            while True:
                try:
                    conn_socket, addr = serv_socket.accept()
                    logging.debug("accepted connection, handshaking")
                    # conn_socket listens to cli_socket
                    parser = Server(conn_socket)
                    parser.main()
                except OSError as e:
                    print(f"Encountered an error while establishing the connection socket: {e}")
                finally:
                    conn_socket.close()
                    logging.debug("closed connection with client")
    except OSError as e:
        print(f"Encountered an error while establishing the welcoming socket: {e}")


if __name__ == "__main__":
    main()
