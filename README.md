# smtp
Fully functioning [SMTP](https://www.rfc-editor.org/rfc/rfc5321) server and client implementations that interact over TCP sockets.

## Server

Usage: `python Server.py [port number]`

SMTP server implementation. The server runs indefinitely and waits for a connection request from a client. Upon reception, it initiates the SMTP handshaking protocol and begins waiting for commands from the client. The server maintains a state machine and, upon full reception of a properly formed sequence of commands, appends the message bodies to the outbound mailbox. 

## Client

Usage: `python Client.py [server hostname] [port number]`

SMTP client implementation. Features a basic CLI email drafting program. Upon completion of a valid email message including sender, recipients, and subject, it opens up a TCP socket to the specified server on the specified port and converts the email message into SMTP commands which are then conveyed over the socket.