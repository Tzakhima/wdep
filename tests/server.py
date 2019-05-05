
'''
v0.1

AWS Deployment Tool
----------------------
This is ser server part. it will listen on socket for the following commands:

stop - will remove the deployment.
moveto <region> - will initiate the same deployment in specified region

'''

import pip
import time
import sys
import socket
import logging
try:
    import boto3
except ImportError:
    pip.main(['install', 'boto3'])
    import boto3


# Set global parameters
HOST = ''
PORT = 9090
BUFSIZE = 1024

# Set logging
logging.basicConfig(filename="/var/log/server.log", level=logging.DEBUG)


def run():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((HOST, PORT))
    logging.info("\nServer started on port: %s" % PORT)
    s.listen(1)
    logging.info("Now listening...\n")
    # conn = client socket
    conn, addr = s.accept()
    while True:
        logging.info('New connection from %s:%d' % (addr[0], addr[1]))
        print('New connection from %s:%d' % (addr[0], addr[1]))
        command = conn.recv(BUFSIZE)
        command_str = command.decode("utf-8")
        if not command:
            break
        # stop command
        elif command_str == 'stop':
            print(command_str)
            conn.send(command)
            logging.info("Got 'stop' command")
        # moveto command
        elif "moveto" in command_str:
            region = command_str.split()[1]
            print(region)
            conn.send(command)
            logging.info("Got 'stop' command")
        # exit
        elif command_str == 'exit':
            conn.send(b'\0')
            conn.close()
            logging.info("Connection closed")
            exit(0)
        else:
            print(command_str)
            conn.send(command)



if __name__ == "__main__":
    run()