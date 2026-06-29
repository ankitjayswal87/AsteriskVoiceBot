import random
import time
import struct
import audioop

class RTPStreamer:

    def __init__(self, sock, ip, port):
        self.sock = sock
        self.ip = ip
        self.port = port

        self.seq = random.randint(0,65535)
        self.timestamp = random.randint(0,0xffffffff)
        self.ssrc = random.randint(1,0xffffffff)

        self.start = time.monotonic()
        self.packet_count = 0
        
    def send_ulaw(self, ulaw):
        while len(ulaw):
            payload = ulaw[:160]
            ulaw = ulaw[160:]

            if len(payload) < 160:
                payload += b'\xff' * (160-len(payload))

            header = struct.pack(
                "!BBHII",
                0x80,
                0,
                self.seq,
                self.timestamp,
                self.ssrc,
            )

            self.sock.sendto(header + payload, (self.ip, self.port))

            self.seq = (self.seq + 1) & 0xffff
            self.timestamp += 160

            self.packet_count += 1

            next_time = self.start + self.packet_count * 0.02
            delay = next_time - time.monotonic()
            if delay > 0:
                time.sleep(delay)
                
    # def stream_ulaw_audio_bytes(sock, ulaw_data, target_ip, target_port):
    #     """
    #     Stream raw G.711 u-law bytes over RTP.

    #     Args:
    #         sock: UDP socket
    #         ulaw_data: bytes object containing raw u-law audio
    #         target_ip: Destination IP
    #         target_port: Destination RTP port
    #     """

    #     # RTP Header Fields
    #     version = 2
    #     padding = 0
    #     extension = 0
    #     csrc_count = 0

    #     byte0 = (version << 6) | (padding << 5) | (extension << 4) | csrc_count

    #     payload_type = 0  # PCMU
    #     marker = 0
    #     byte1 = (marker << 7) | payload_type

    #     # Random RTP identifiers
    #     sequence_number = random.randint(0, 65535)
    #     timestamp = random.randint(0, 0xFFFFFFFF)
    #     ssrc = random.randint(1, 0xFFFFFFFF)

    #     CHUNK_SIZE = 160          # 20 ms @ 8kHz
    #     FRAME_DURATION = 0.020    # 20 ms

    #     print(f"Streaming {len(ulaw_data)} bytes to {target_ip}:{target_port}")

    #     #start_time = time.time()
    #     start_time = time.monotonic()
    #     packet_count = 0

    #     offset = 0
    #     data_len = len(ulaw_data)

    #     while offset < data_len:
    #         payload = ulaw_data[offset:offset + CHUNK_SIZE]
    #         offset += CHUNK_SIZE
    #         print("PAYLOAD SIZE",len(payload))

    #         # Pad last packet with silence if needed
    #         if len(payload) < CHUNK_SIZE:
    #             payload += b'\xff' * (CHUNK_SIZE - len(payload))

    #         # RTP Header
    #         rtp_header = struct.pack(
    #             "!BBHII",
    #             byte0,
    #             byte1,
    #             sequence_number,
    #             timestamp,
    #             ssrc
    #         )

    #         # Send RTP packet
    #         sock.sendto(rtp_header + payload, (target_ip, target_port))

    #         # Update RTP state
    #         sequence_number = (sequence_number + 1) & 0xFFFF
    #         timestamp = (timestamp + CHUNK_SIZE) & 0xFFFFFFFF
    #         packet_count += 1

    #         # Maintain 20 ms packet interval
    #         next_transmission = start_time + (packet_count * FRAME_DURATION)
    #         sleep_time = next_transmission - time.monotonic()
    #         if sleep_time > 0:
    #             time.sleep(sleep_time)

    #     print("Streaming completed successfully.")

    def stream_ulaw_audio(self,file_path):
        # 1. Setup UDP Socket
        #sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        # 2. Initialize RTP Variables
        version = 2
        padding = 0
        extension = 0
        csrc_count = 0
        
        # Pack the first byte (Version, P, X, CC)
        # Binary: 10 0 0 0000 = 0x80
        byte0 = (version << 6) | (padding << 5) | (extension << 4) | csrc_count
        
        # Payload Type: 0 is the standard ID for PCMU (G.711 u-law)
        payload_type = 0 
        marker = 0
        byte1 = (marker << 7) | payload_type
        
        # Randomize initial sequence, timestamp, and SSRC
        # sequence_number = random.randint(1000, 50000)
        # timestamp = random.randint(100000, 5000000)
        # ssrc = random.randint(100000, 999999)
        sequence_number = random.randint(0, 65535)
        timestamp = random.randint(0, 0xFFFFFFFF)
        ssrc = random.randint(1, 0xFFFFFFFF)
        
        # 3. Define Packet Timing and Size
        # For 8000Hz u-law, 20ms of audio is exactly 160 bytes (8000 * 0.02)
        CHUNK_SIZE = 160 
        FRAME_DURATION = 0.020 # 20 milliseconds
        
        print(f"Streaming {file_path} to {self.ip}:{self.port}...")
        
        with open(file_path, "rb") as f:
            start_time = time.time()
            packet_count = 0
            
            while True:
                # Read a 20ms chunk of raw u-law audio
                payload = f.read(CHUNK_SIZE)
                if not payload:
                    break # End of file
                    
                # Handle short final packets by padding with silent u-law bytes (0xFF)
                if len(payload) < CHUNK_SIZE:
                    payload += b'\xff' * (CHUNK_SIZE - len(payload))
                
                # 4. Build the 12-Byte Big-Endian Header
                # Format string explanation:
                # ! = Big-Endian
                # B = 1 byte unsigned char
                # H = 2 byte unsigned short (Sequence Number)
                # I = 4 byte unsigned int (Timestamp)
                # I = 4 byte unsigned int (SSRC)
                rtp_header = struct.pack(
                    "!BBHII", 
                    byte0, 
                    byte1, 
                    sequence_number, 
                    timestamp, 
                    ssrc
                )
                
                # Combine Header and Audio Payload
                rtp_packet = rtp_header + payload
                
                # 5. Transmit to Asterisk Port
                self.sock.sendto(rtp_packet, (self.ip, self.port))
                
                # 6. Increment Variables for Next Packet
                sequence_number = (sequence_number + 1) & 0xFFFF # Keep within 16-bit bounds
                timestamp += CHUNK_SIZE # Advance timestamp by number of samples sent
                packet_count += 1
                
                # 7. Strict Timing Loop to maintain 20ms pacing
                next_transmission = start_time + (packet_count * FRAME_DURATION)
                sleep_time = next_transmission - time.time()
                if sleep_time > 0:
                    time.sleep(sleep_time)

        #sock.close()
        print("Streaming completed successfully.")
                
class Sampler:
    def __init__(self, input_rate, output_rate):
        self.input_rate = input_rate
        self.output_rate = output_rate

    def pcm24k_to_ulaw(self, pcm_bytes, state=None):
        """
        Convert 16-bit PCM at input_rate to μ-law at output_rate.

        Args:
            pcm_bytes: PCM audio bytes.
            state: Previous state returned by audioop.ratecv().

        Returns:
            (ulaw_bytes, new_state)
        """
        pcm_out, new_state = audioop.ratecv(
            pcm_bytes,
            2,                  # sample width (16-bit)
            1,                  # mono
            self.input_rate,
            self.output_rate,
            state
        )

        ulaw = audioop.lin2ulaw(pcm_out, 2)

        return ulaw, new_state