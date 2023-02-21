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

# logging.basicConfig(format='%(levelname)s: %(message)s', level=logging.DEBUG)
logging.basicConfig(format="%(message)s", level=logging.INFO)

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

    def send(self, s: str):
        logging.debug(f"sending: {s}".rstrip())
        self.cli_socket.send(s.encode())

    def main(self):
        if self.state == self.state.ERROR:
            return

        msg_res = self.get_message()
        if msg_res is None:
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
                            # n = next(to_stream)
                            # logging.debug(n)
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

        domain = re.match(r"^([a-zA-Z][a-zA-Z0-9]*.)*([a-zA-Z][a-zA-Z0-9]*)$", buf)
        if not domain:
            return "Invalid domain name"

        return ""

    @staticmethod
    def get_message() -> (str, list[str], str, str):
        try:
            # Prompt From:
            from_ = None
            while from_ is None:
                path = input("From:\n")
                res = Client.parse_path(path)
                if res != "":
                    print(res)
                else:
                    from_ = path

            # Prompt To:
            to = None
            while not to:
                paths = re.split(r",[ \t]*", input("To:\n"))
                for p in paths:
                    res = Client.parse_path(p)
                    if res != "":
                        print(res)
                        continue
                to = paths

            # Prompt Subject:
            subj = input("Subject:\n")

            # Prompt Message:
            print("Message:")
            line = None
            lines = []
            while line != ".":
                if line is not None:
                    lines.append(line)
                line = input("")
            msg = "\n".join(lines)

            return from_, to, subj, msg
        except EOFError:
            return None

    def quit(self):
        # self.send("QUIT\n")
        self.state = self.State.QUIT

    def error(self, msg: str):
        # TODO: handle SMTP error
        print(f"Encountered an SMTP error: {repr(msg)}")
        self.state = self.State.ERROR

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

        if port < 1 or port > 65536:
            print(f"Port must be 1-65536")
            return
        client = Client(hostname, port)
        client.main()


if __name__ == '__main__':
    main()
