"""
I certify that no unauthorized assistance has been received or given in the completion of this work
Signed: Oliver Chen
Date: February 21, 2023
"""

import sys
import os

"""
Checklist:

- [x] Take hostname and port number from command line arguments
- [ ]
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
        self.code = -1

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
        # TODO: review code parsing
        code = self.resp_number()
        if self.whitespace() and self.arbitrary() and self.crlf():
            return code
        return -1

    def resp_number(self):
        # TODO: review code parsing
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


class Client:
    def __init__(self, path):
        self.state = 0
        self.path = path

    def main(self):
        lines = self.get_lines()
        if lines is None:
            return

        for line in lines:
            # debug(f"{self.state=}, {line=}")
            match self.state:
                case 0:
                    # expecting From:
                    self.parse_from(line)
                case 1:
                    # expecting To:
                    if line.startswith("To: "):
                        sys.stdout.write(f"RCPT TO: {line[4:].strip()}\n")
                        self.react_to_response(250, 2)
                    else:
                        self.quit()
                case 2:
                    # expecting To: or data message
                    if line.startswith("To: "):
                        sys.stdout.write(f"RCPT TO: {line[4:].strip()}\n")
                        self.react_to_response(250, 2)
                    else:
                        sys.stdout.write("DATA\n")
                        self.react_to_response(354, 3)
                        if self.state == -1:
                            break
                        self.read_message(line)
                case 3:
                    # expecting data message
                    self.read_message(line)
                case _:
                    break
        if self.state == 3:
            # valid end state of message
            self.close_message()
        if self.state != -1:
            self.quit()


    def get_lines(self):
        if self.path == "" or not os.path.exists(self.path):
            return None
        with open(self.path, "r+") as fp:
            return fp.readlines()

    def quit(self):
        sys.stdout.write("QUIT\n")
        self.state = -1

    def parse_from(self, line):
        if line.startswith("From: "):
            sys.stdout.write(f"MAIL FROM: {line[6:].strip()}\n")
            self.react_to_response(250, 1)
        else:
            self.quit()

    def close_message(self):
        sys.stdout.write(".\n")
        self.react_to_response(250, 0)

    def read_message(self, line: str):
        if line.startswith("From: "):
            # new message, reset state
            self.close_message()
            self.parse_from(line)
        else:
            self.state = 3
            sys.stdout.write(line)

    @staticmethod
    def wait_for_response() -> (int, str):
        for line in sys.stdin:
            return ResponseParser(line).parse_code(), line
        return -1, None

    def react_to_response(self, expected_code: int, next_state: int = -1):
        (code, message) = Client.wait_for_response()
        if message is not None:
            sys.stderr.write(message)
        debug(f"{code=}, {message=}")
        if code != expected_code:
            self.quit()
        else:
            self.state = next_state


def main():
    hostname = None
    port = -1
    if len(sys.argv) > 2:
        try:
            hostname = sys.argv[1]
            port = int(sys.argv[2])
        except IndexError:
            sys.stderr.write("Not enough arguments, expected hostname followed by port number\n")
        except ValueError:
            sys.stderr.write(f"Argument {sys.argv[2]} is not a valid port number\n")
    # TODO: modify client to prompt message components
    client = Client()
    client.main()


if __name__ == '__main__':
    main()
