import socket
import threading
import datetime
import curses
import time
import re
import os

# ANSI color codes (fallback if curses isn't available)
RESET = '\033[0m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'

log_sources = {}  # Dictionary to store logs by source address
current_source = None
screen = None


def get_wifi_ip_netifaces():
    try:
        for interface in netifaces.interfaces():
            print(f"Interface: {interface}") #add this line.
            addresses = netifaces.ifaddresses(interface)
            if netifaces.AF_INET in addresses:
                for addr_info in addresses[netifaces.AF_INET]:
                    ip_address = addr_info['addr']
                    print(f"  IP Address: {ip_address}") #add this line.
                    if ip_address.startswith('192.168.'):
                        return ip_address
        return None
    except Exception as e:
        print(f"Error getting WiFi IP: {e}")
        return None

def get_wifi_ip():
    try:
        wifi_ip = socket.gethostbyname(socket.gethostname())
        return wifi_ip
    except Exception as e:
        print(f"Error getting WiFi IP: {e}")
        return None

def extract_imei(message):
    """Extracts IMEI from the log message."""
    #match = re.search(r'IMEI:(\s{15})', message)
    match = re.search(r'IMEI:([^\s]+)', message)
    if match:
        return match.group(1)
    return None

def save_log_to_file(imei, log_entry):
    """Saves the log entry to a file."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    log_file = os.path.join(log_dir, f"{imei}.log")
    with open(log_file, "a") as f:
        f.write(log_entry + "\n")

def handle_client(data, address):
    """Handles incoming UDP log messages and stores them."""
    print(f"Received data from {address}: {data}") # print the raw data.
    try:
        message = data.decode('utf-8').strip()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        imei = extract_imei(message)
        if imei is None:
            imei = f"Unknown_{address}"
        else:
            # Remove the IMEI from the message
            message = re.sub(r'IMEI:([^\s]+)', '', message).strip()
        log_entry = f"{timestamp} - {message}"

        if imei not in log_sources:
            log_sources[imei] = []
        log_sources[imei].append(log_entry)
        print("WRITING: ",imei," - ",log_entry)
        update_screen()

    except UnicodeDecodeError:
        log_entry = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Received non-UTF-8 data from {address}"
        if imei not in log_sources:
            log_sources[imei] = []
        log_sources[imei].append(log_entry)
        update_screen()

    except Exception as e:
        log_entry = f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - Error processing message from {address}: {e}"
        if imei not in log_sources:
            log_sources[imei] = []
        log_sources[imei].append(log_entry)
        
        update_screen()

def udp_server(host, port):
    """Sets up and runs the UDP server."""
    try:
        print("Starting UDP server...",flush=True) #add this line
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host, port))
        print(f"UDP server listening on {host}:{port}",flush=True)
        print("Server binded",flush=True) #add this line

        while True:
            data, address = sock.recvfrom(1024)
            threading.Thread(target=handle_client, args=(data, address)).start()

    except OSError as e:
        print(f"Error starting UDP server: {e}")
    except KeyboardInterrupt:
        print("\nUDP server stopped by user.")
    finally:
        if 'sock' in locals():
            sock.close()

def update_screen():
    """Updates the curses screen with log data."""
    global current_source, screen, log_sources
    if screen is None:
        return
    
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
    curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_RED)
    curses.init_pair(5, curses.COLOR_RED, curses.COLOR_YELLOW)

    screen.clear()
    sources = list(log_sources.keys())

    if not sources:
        local_ip = get_wifi_ip_netifaces()
        screen.addstr(0, 0, f"Server listening on {local_ip}:{PORT}")
        screen.refresh()
        return

    if current_source is None and sources:
        current_source = sources[0]

    if current_source not in sources:
        if sources:
            current_source = sources[0]
        else:
            current_source = None #in case sources is empty.

    if current_source is not None:
        screen.addstr(0, 0, f"Current Source: {current_source}")
        screen.addstr(1, 0, "Sources: " + ", ".join([f"{i+1}. {s}" for i, s in enumerate(sources)]))

        if current_source in log_sources:
            logs = log_sources[current_source][-screen.getmaxyx()[0] + 3:]

            for i, log in enumerate(logs):
                try:
                    log.replace('\0', '').strip()
                    log = re.sub(r'\x00', '', log) #remove null characters.
                    log = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', log) #remove all control characters.
                    save_log_to_file(current_source, log)
                    if "[WARNING]" in log:
                        screen.addstr(i + 3, 0, log, curses.color_pair(5))
                    elif "[ERROR]" in log:
                        screen.addstr(i + 3, 0, log, curses.color_pair(2))
                    elif "[INFO]" in log:
                        screen.addstr(i + 3, 0, log, curses.color_pair(1))
                    elif "[NOTICE]" in log:
                        screen.addstr(i + 3, 0, log, curses.color_pair(3))
                    elif "[DEBUG]" in log:
                        screen.addstr(i + 3, 0, log, curses.color_pair(4))        
                    else:
                        screen.addstr(i + 3, 0, log)
                except curses.error as e:
                    screen.addstr(i + 3, 0, f"Error displaying log: {e}", curses.color_pair(2))
                except Exception as e:
                    screen.addstr(i+3, 0, f"Error processing log: {e}", curses.color_pair(2))
    else:
        screen.addstr(0,0, "No sources available")
    screen.refresh()

def main(stdscr):
    """Main function for curses interface."""
    print("STARTING SERVER",flush=True)
    global screen
    screen = stdscr
    screen.nodelay(True)  # Non-blocking input

    threading.Thread(target=udp_server, args=(HOST, PORT), daemon=True).start()

    while True:
        update_screen()
        key = screen.getch()
        if key != -1:
            sources = list(log_sources.keys())
            if ord('1') <= key <= ord('9'):
                source_index = key - ord('1')
                if 0 <= source_index < len(sources):
                    global current_source
                    current_source = sources[source_index]
            if key == ord('q'):
                break
        time.sleep(0.1)

if __name__ == "__main__":
    HOST = '0.0.0.0'
    PORT = 514

    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        print("Server stopped.",flush=True)
    finally:
        print("Exiting",flush=True)
