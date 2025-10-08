import argparse
from modSim.server import Server
import logging

def main():
    parser = argparse.ArgumentParser(description="Start the Modbus Simulator API server.")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    # Configure the root logger
    log_level = logging.INFO
    if args.debug:
        log_level = logging.DEBUG

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler()]
    )

    Server().run()

if __name__ == "__main__":
    main()
