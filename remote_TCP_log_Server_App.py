import socket
import threading
import datetime
import re
import os
import json
import time
import struct

# ANSI color codes for terminal output
RESET = '\033[0m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
CYAN = '\033[96m'
MAGENTA = '\033[95m'

log_sources = {}
current_source = None

def get_wifi_ip():
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception as e:
        print(f"{RED}Error getting IP: {e}{RESET}")
        return None

def extract_imei(message):
    try:
        log_data = json.loads(message)
        return log_data.get('IMEI')
    except json.JSONDecodeError:
        match = re.search(r'"IMEI":"([^"]+)"', message)
        return match.group(1) if match else None
    except Exception as e:
        print(f"{RED}IMEI extraction error: {e}{RESET}")
        return None

def save_log_to_file(imei, log_entry):
    try:
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{imei}.log")
        with open(log_file, "a") as f:
            f.write(log_entry + "\n")
        print(f"{GREEN}Log saved to {MAGENTA}{log_file}{RESET}")
        return True
    except Exception as e:
        print(f"{RED}File save error: {e}{RESET}")
        return False

def handle_client(client_socket, address):
    print(f"{CYAN}New connection from {address}{RESET}")
    buffer = ""
    try:
        while True:
            data = client_socket.recv(1024)
            if not data:
                break
            
            # Decode and add to buffer
            try:
                decoded_data = data.decode('utf-8')
            except UnicodeDecodeError:
                decoded_data = data.decode('utf-8', errors='replace')
            
            buffer += decoded_data
            
            # Process complete lines from buffer
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                raw_message = line.strip()
                
                if not raw_message:
                    continue
                    
                print(f"{CYAN}Received: {raw_message}{RESET}")
                
                try:
                    # Try to parse as JSON
                    log_data = json.loads(raw_message)
                    
                    # Extract IMEI using original logic
                    imei = log_data.get("IMEI") or extract_imei(raw_message) or f"Unknown_{address[0]}"
                    
                    # Build timestamp
                    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    # Build log parts (preserving original logic)
                    log_parts = [f"{timestamp} - [{log_data.get('level', 'UNKNOWN').upper()}]"]
                    
                    # Add file:line if both are valid (not "UNKNOWN" or line is not 0)
                    file_part = log_data.get('file', 'UNKNOWN')
                    line_part = log_data.get('line', 'UNKNOWN')
                    if file_part != 'UNKNOWN' and line_part != 'UNKNOWN' and str(line_part) != '0':
                        log_parts.append(f"{file_part}:{line_part}")
                    
                    # Add function if valid (not "UNKNOWN")
                    function_part = log_data.get('function', 'UNKNOWN')
                    if function_part != 'UNKNOWN':
                        log_parts.append(function_part)
                    
                    # Always add data (even if UNKNOWN)
                    data_part = log_data.get('data', 'UNKNOWN')
                    log_parts.append(data_part)
                    
                    # Join all valid parts
                    log_entry = " - ".join(log_parts)
                    
                    # Remove the unwanted parts (preserving original logic)
                    log_entry = log_entry.replace(" - UNKNOWN:0", "").replace(" - UNKNOWN", "")
                    
                    # Add to log sources (preserving original logic)
                    if imei not in log_sources:
                        log_sources[imei] = []
                        print(f"{GREEN}New device: {MAGENTA}{imei}{RESET}")
                    
                    log_sources[imei].append(log_entry)
                    save_log_to_file(imei, log_entry)
                    
                except json.JSONDecodeError:
                    # Handle malformed JSON (preserving original error handling)
                    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    error_msg = f"{timestamp} - [ERROR] - Malformed message: {raw_message}"
                    save_log_to_file("invalid_json", error_msg)
                    print(f"{RED}Malformed JSON message ignored{RESET}")
                    
                except Exception as e:
                    print(f"{RED}Client error: {e}{RESET}")
            
            # Handle case where buffer has content but no newline (partial message)
            # This preserves any incomplete JSON that might arrive in next packet
            
    except Exception as e:
        print(f"{RED}Connection error: {e}{RESET}")
    finally:
        client_socket.close()
        print(f"{YELLOW}Connection closed: {address}{RESET}")

def tcp_server(host, port):
    try:
        print(f"{GREEN}Starting server on {host}:{port}{RESET}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Preserve original socket options
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except AttributeError:
            print(f"{YELLOW}SO_REUSEPORT not available{RESET}")
        
        linger = struct.pack('ii', 1, 0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
        
        sock.bind((host, port))
        sock.listen(5)
        print(f"{GREEN}Server started successfully{RESET}")
        
        while True:
            client_socket, address = sock.accept()
            client_thread = threading.Thread(
                target=handle_client,
                args=(client_socket, address),
                daemon=True
            )
            client_thread.start()
            
    except Exception as e:
        print(f"{RED}Server error: {e}{RESET}")
    finally:
        if 'sock' in locals():
            sock.close()
        print(f"{YELLOW}Server socket closed{RESET}")

if __name__ == "__main__":
    HOST = '127.0.0.1'
    PORT = 8000
    try:
        tcp_server(HOST, PORT)
    except KeyboardInterrupt:
        print(f"\n{RED}Server shutdown initiated{RESET}")
