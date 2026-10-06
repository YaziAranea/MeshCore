"""Read-only example. Explicit target required; no secrets or raw frames printed."""
import argparse
from smartui_cli import CliClient, CliError
import transports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--usb", metavar="PORT")
    target.add_argument("--tcp", metavar="HOST")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    transport = None
    try:
        transport = transports.usb(args.usb) if args.usb else transports.tcp(args.tcp, args.port)
        client = CliClient(transport.exchange, transport.close)
        hello = client.connect()
        print("Local CLI version:", hello["version"], "write:", hello["write"])
        for key in ("volume", "muted", "agc_reset"):
            try:
                print(key + ":", client.field("get", key))
            except CliError as error:
                if error.reason == "unsupported":
                    print(key + ": unsupported")
                else:
                    raise
    except (CliError, OSError, ImportError) as error:
        # External exceptions may include endpoints/credentials: don't print them.
        print(str(error) if isinstance(error, CliError) else "Transport unavailable.")
        return 1
    finally:
        if transport:
            transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
