"""
I certify that no unauthorized assistance has been received or given in the completion of this work
Signed: Oliver Chen
Date: February 21, 2023
"""

import sys
from enum import Enum, auto
from socket import *
import re
import logging

# logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
logging.basicConfig(format="%(message)s", level=logging.INFO)


class State(Enum):
    HELO = auto()
    FROM = auto()
    TO = auto()
    DATA = auto()
    QUIT = auto()
    ERROR = auto()


def parse_path(path) -> str:
    buf = path
    local_part = re.match(r"^[^<>()[\]@.,;:\\\"\s]+", buf)
    if not local_part:
        return "Invalid local name"
    buf = buf.lstrip(local_part.group(0))

    at_sign = re.match(r"^@", buf)
    if not at_sign:
        return "Missing @"
    buf = buf.lstrip("@")

    domain = re.match(r"^((?:(?:[a-zA-Z][a-zA-Z0-9]*)+\.)*(?:[a-zA-Z][a-zA-Z0-9]*)+)[ \t]*\n?$",
                      buf)
    if not domain:
        return "Invalid domain name"

    return ""


def get_message() -> (str, list[str], str, str):
    try:
        from_ = None
        while from_ is None:
            print("From:")
            line = sys.stdin.readline()
            res = parse_path(line)
            if res != "":
                print(res)
            else:
                from_ = line.rstrip("\n")

        to = None
        while to is None:
            print("To:")
            paths = []
            line = sys.stdin.readline()
            for p in re.split(r",[ \t]*", line):
                res = parse_path(p)
                if res != "":
                    print(res)
                    to = None
                    break
                else:
                    paths.append(p.rstrip("\n"))
                    to = paths

        print("Subject:")
        subj = sys.stdin.readline().rstrip("\n")

        print("Message:")
        line = None
        lines = []
        while line != ".\n":
            if line is not None:
                lines.append(line.rstrip("\n"))
            line = sys.stdin.readline()
        msg = "\n".join(lines)

        return from_, to, subj, msg
    except EOFError:
        return None


def parse_code(message: str) -> int:
    match = re.match(r"^(\d{3})\s+.*\n$", message)
    if not match:
        return -1
    return int(match.group(1))


class Client:
    def __init__(self, hostname, port):
        self.state = State.HELO
        self.server = (hostname, port)
        try:
            self.cli_socket = socket(AF_INET, SOCK_STREAM)
            self.cli_socket.connect(self.server)
            logging.debug(f"connected to {hostname}")
        except OSError:
            self.state = State.ERROR

    def send(self, s: str):
        logging.debug(f"sending: {s}".rstrip())
        self.cli_socket.send(s.encode())

    def main(self):
        if self.state == State.ERROR:
            return

        msg_res = get_message()
        if msg_res is None:
            return
        from_, to, subj, msg = msg_res

        self.react_to_response(220, State.FROM)
        if self.state not in [State.QUIT, State.ERROR]:
            self.send(f"HELO {gethostname()}\n")

        to_stream = iter(to)
        while self.state not in (State.QUIT, State.ERROR):
            try:
                match self.state:
                    case State.FROM:
                        # command MAIL FROM:
                        self.send(f"MAIL FROM: <{from_}>\n")
                        self.react_to_response(250, State.TO)
                    case State.TO:
                        # command(s) RCPT TO:
                        try:
                            self.send(f"RCPT TO: <{next(to_stream)}>\n")
                            self.react_to_response(250, State.TO)
                        except StopIteration:
                            self.react_to_response(250, State.DATA)
                    case State.DATA:
                        # command DATA + message
                        self.send("DATA\n")
                        self.react_to_response(354, State.DATA)
                        self.send(f"From: <{from_}>\n"
                                  f"To: {', '.join([f'<{path}>' for path in to])}\n"
                                  f"Subject: {subj}\n\n"
                                  f"{msg}\n"
                                  f".\n"
                                  )
                        self.react_to_response(250)
                    case State.QUIT:
                        self.send("QUIT\n")
                        self.react_to_response(221)
            except OSError as e:
                print(f"Encountered a socket error: '{e}'")
                break

        self.cli_socket.close()

    def get_input(self, prompt: str):
        print(prompt)
        out = None
        for line in sys.stdin:
            out = line.rstrip("\n")
            break
        if out is None:
            self.state = State.ERROR
            return None
        return out

    def error(self, msg: str):
        print(f"Encountered an SMTP error: {msg}".rstrip())
        self.state = State.ERROR

    def react_to_response(self, expected_code: int, next_state: State = State.QUIT) -> bool:
        try:
            response = self.cli_socket.recv(1024)
        except OSError as e:
            print(f"Encountered a socket error: {e}")
            return False

        message = response.decode()
        code = parse_code(message)
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
        try:
            hostname = sys.argv[1]
            port = int(sys.argv[2])

        except IndexError:
            logging.debug("Not enough arguments, expected hostname followed by port number\n")
        except ValueError:
            logging.debug(f"Argument {sys.argv[2]} is not a valid port number\n")

        if port < 1 or port > 65536:
            print(f"Port must be 1-65536")
            return
        client = Client(hostname, port)
        client.main()


if __name__ == '__main__':
    main()
