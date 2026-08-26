"""
Example script to start a flow cell check.

Example usage might be:

python ./python/minknow_api/examples/start_flow_cell_check.py \
    --host localhost --position X1


This will start a flow cell check on position X1 of the local machine.

"""  # noqa W605

import argparse
import logging
import sys

# minknow_api.manager supplies "Manager" a wrapper around MinKNOW's Manager gRPC API with utilities
# for querying sequencing positions + offline basecalling tools.
from minknow_api.manager import Manager

# We need `find_protocol` to search for the required protocol given a kit + product code.
from minknow_api.tools import protocols


def _load_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def parse_args():
    """Build and execute a command line argument for starting a protocol.

    Returns:
        Parsed arguments to be used when starting a protocol.
    """

    parser = argparse.ArgumentParser(
        description="""
        Run a sequencing protocol in a running MinKNOW instance.
        """
    )

    parser.add_argument(
        "--host",
        default="localhost",
        help="IP address of the machine running MinKNOW (defaults to localhost)",
    )
    parser.add_argument(
        "--port",
        help="Port to connect to on host (defaults to standard MinKNOW port based on tls setting)",
    )
    parser.add_argument(
        "--api-token",
        default=None,
        help="Specify an API token to use, should be returned from the sequencer as a developer API token.",
    )
    parser.add_argument(
        "--client-cert-chain",
        type=_load_file,
        default=None,
        help="Path to a PEM-encoded X.509 certificate chain for client authentication.",
    )
    parser.add_argument(
        "--client-key",
        type=_load_file,
        default=None,
        help="Path to a PEM-encoded private key for client certificate authentication.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    position_args = parser.add_mutually_exclusive_group(required=True)
    position_args.add_argument(
        "--position",
        help="position on the machine (or MinION serial number) to run the protocol at. "
        "(specify this or --flow-cell-id or --sample-sheet)",
    )
    position_args.add_argument(
        "--flow-cell-id",
        metavar="FLOW-CELL-ID",
        help="ID of the flow-cell on which to run the protocol. "
        "(specify this or --position or --sample-sheet)",
    )

    args = parser.parse_args()

    return args


def main():
    """Entrypoint to start flow cell check example"""
    # Parse arguments to be passed to started protocols:
    args = parse_args()

    # Specify --verbose on the command line to get extra details about the actions performed
    if args.verbose:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    # Construct a manager using the host + port provided:
    manager = Manager(
        host=args.host,
        port=args.port,
        developer_api_token=args.api_token,
        client_certificate_chain=args.client_cert_chain,
        client_private_key=args.client_key,
    )

    connections = []

    for position in manager.flow_cell_positions():
        con = position.connect()
        if args.flow_cell_id:
            # Check if the flow cell ID matches the one provided
            flow_cell_info = con.device.get_flow_cell_info()
            if flow_cell_info.flow_cell_id == args.flow_cell_id:
                connections.append((position, con))
                break
        elif args.position:
            # Check if the position matches the one provided
            if position.name == args.position:
                connections.append((position, con))
                break
    else:
        # If no position was found, print an error message and exit
        print("No matching position found for --position or --flow-cell-id")
        sys.exit(1)

    # Check if a flowcell is available for sequencing
    for pos, position_connection in connections:
        flow_cell_info = position_connection.device.get_flow_cell_info()
        if not flow_cell_info.has_flow_cell:
            print(
                "No flow cell present in position {}".format(position_connection.name)
            )
            sys.exit(1)

        flow_cell_info = position_connection.device.get_flow_cell_info()
        product_code = flow_cell_info.user_specified_product_code
        if not product_code:
            product_code = flow_cell_info.product_code

        # Find the protocol identifier for the required protocol:
        protocol_info = protocols.find_protocol(
            position_connection,
            product_code=product_code,
            kit="",
            config_name=None,
            experiment_type="platform QC",
        )

        result = position_connection.protocol.start_protocol(
            identifier=protocol_info.identifier,
            args=[],
        )

        print("Started flow cell check:")
        print("    run_id={}".format(result.run_id))
        print("    position={}".format(pos.name))
        print("    flow_cell_id={}".format(flow_cell_info.flow_cell_id))
        print(
            "    user_specified_flow_cell_id={}".format(
                flow_cell_info.user_specified_flow_cell_id
            )
        )


if __name__ == "__main__":
    main()
