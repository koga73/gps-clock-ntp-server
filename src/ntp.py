import _thread
import socket
import ustruct
import errno

# NTP timestamp starts Jan 1, 1900. Unix epoch starts Jan 1, 1970
# Difference is 2,208,988,800 seconds
_EPOCH_OFFSET = 2208988800
# Precise 32-bit fractional conversion scale (2^32 / 1,000,000 = 4294.967296)
_FRACTIONAL_SCALE = 4294.967296

_PRECISION_MILLISECOND = -10 # 2 ^ -10 = ~1 millisecond: Standard precision for a microcontroller
_PRECISION_MICROSECOND = -20 # 2 ^ -20 = ~1 microsecond

POLL_INTERVAL = 6 # 2 ^ 6 = 64 seconds: Standard starting default interval for most Linux systems
PRECISION = _PRECISION_MICROSECOND

class NtpServer():
    def __init__(self, time_func):
        self._lock = _thread.allocate_lock()

        self.time_func = time_func
        
        self._server = None
        self._transport = None
        self._protocol = None
    
    def start(self):
        self._server = self._udp_server(
            NtpProtocol,
            "0.0.0.0",
            123
        )
    
    def stop(self):
        if (self._protocol):
            self._protocol = None
        
        if (self._transport):
            self._transport.close()
            self._transport = None

        if (self._server):
            self._server.close()
            self._server = None

    def _udp_server(self, protocol, host, port):
        transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        transport.bind((host, port))
        transport.setblocking(False)
        
        self._transport = transport
        self._protocol = protocol(transport)

    def udp_loop(self):
        if (not self._transport or not self._protocol):
            raise ValueError("ntp server not started")
        
        try:
            data, addr = self._transport.recvfrom(48)
            recv_time = self.time_func()
            self._protocol.datagram_received(data, addr, recv_time, self.time_func)
        
        except ValueError as e:
            with self._lock:
                print("ntp error: " + str(e))
        
        except OSError as e:
            # If transport is closed, break the loop
            if e.args[0] == errno.EBADF:
                return True
        
        return False

class NtpProtocol():
    def __init__(self, transport):
        self._lock = _thread.allocate_lock()

        self.transport = transport

    def datagram_received(self, data, addr, recv_time, time_func):
        # NTP packages are ALWAYS 48 bytes
        if (len(data) != 48):
            raise ValueError("invalid ntp packet length: " + str(len(data)))
        
        self.process_packet(data, addr, recv_time, time_func)
    
    def process_packet(self, data, addr, recv_time, time_func):
        with self._lock:
            print(f"\nntp request from {addr[0]}")

        # Extract Client Transmit Timestamp (bytes 40-47 in request)
        client_transmit_timestamp = data[40:48]

        # Mirror the version number from the client request (bits 5-3 of byte 0)
        client_vn = (data[0] >> 3) & 0x7

        # T2: Receive timestamp — captured at recvfrom, before any processing delay
        recv_sec, recv_frac = recv_time
        recv_ntp_sec = recv_sec + _EPOCH_OFFSET
        recv_ntp_frac = int(recv_frac * _FRACTIONAL_SCALE)

        # Construct NTP Response Packet (48 bytes)
        response = bytearray(48)
        response[0] = (client_vn << 3) | 0x04   # LI=0 (no warning), VN=mirrored from client, Mode=4 (server)
        response[1] = 1                         # Stratum 1 (Primary reference)
        response[2] = POLL_INTERVAL             # Poll interval
        response[3] = PRECISION & 0xFF          # Precision encoded to fit in a byte

        # Reference ID
        response[12:16] = b'GPSD'

        # Reference Timestamp (last time synced, approximation: same as receive)
        response[16:20] = ustruct.pack("!I", recv_ntp_sec)
        response[20:24] = ustruct.pack("!I", recv_ntp_frac)
        
        # Origin Timestamp (echo client transmit)
        response[24:32] = client_transmit_timestamp

        # Receive Timestamp (T2: when packet arrived at server)
        response[32:36] = ustruct.pack("!I", recv_ntp_sec)
        response[36:40] = ustruct.pack("!I", recv_ntp_frac)

        # T3: Transmit timestamp — captured just before sending to exclude server processing time
        xmit_sec, xmit_frac = time_func()
        xmit_ntp_sec = xmit_sec + _EPOCH_OFFSET
        xmit_ntp_frac = int(xmit_frac * _FRACTIONAL_SCALE)

        # Transmit Timestamp (T3: when packet leaves server)
        response[40:44] = ustruct.pack("!I", xmit_ntp_sec)
        response[44:48] = ustruct.pack("!I", xmit_ntp_frac)

        # Send packet back to client
        self.transport.sendto(response, addr)
