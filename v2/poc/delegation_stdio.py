"""MCP stdio transport to one operator-owned, frozen delegation capability.

No package discovery, credentials, commands or model selection are accepted here.
The native sandbox's existing Unix-socket permission is sufficient.
"""
import socket,sys

def main(path):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.connect(path)
        reader=connection.makefile('rb')
        for line in sys.stdin.buffer:
            connection.sendall(line)
            # JSON-RPC notifications have no response.
            import json
            if 'id' in json.loads(line):
                answer=reader.readline()
                if not answer:raise RuntimeError('Delegation operator disconnected')
                sys.stdout.buffer.write(answer);sys.stdout.buffer.flush()

if __name__=='__main__':main(sys.argv[1])
