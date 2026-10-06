"""Read-only SmartUI inspector. Does not configure Wi-Fi or change settings."""

import argparse
import json

from smartui_api import SmartUIClient
from transports import TcpTransport, UsbTransport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="transport", required=True)
    tcp = sub.add_parser("tcp", help="already-configured Wi-Fi companion session")
    tcp.add_argument("host")
    tcp.add_argument("port", type=int)
    usb = sub.add_parser("usb", help="USB in framed companion mode, not text console")
    usb.add_argument("port")
    usb.add_argument("--baudrate", type=int, default=115200)
    args = parser.parse_args()
    transport = (TcpTransport(args.host, args.port) if args.transport == "tcp"
                 else UsbTransport(args.port, baudrate=args.baudrate))
    with transport:
        transport.begin_companion_session()
        client = SmartUIClient(transport.exchange)
        result = {"hello": client.hello(), "caps": client.caps(),
                  "settings": client.get(), "connection": client.connection()}
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
