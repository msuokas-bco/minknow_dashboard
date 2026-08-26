import argparse
import csv
import datetime

# minknow_api.manager supplies "Manager" a wrapper around MinKNOW's Manager gRPC API with utilities for
# querying sequencing positions + offline basecalling tools.
from minknow_api.manager import Manager
from minknow_api.protocol_pb2 import FilteringInfo


def to_datetime(date_str):
    if date_str is None:
        return None
    return datetime.datetime.strptime(date_str, "%Y-%m-%d")


def main():
    """Main entrypoint for list_flow_cell_check example"""
    parser = argparse.ArgumentParser(
        description="List historical flow cell checks on a host."
    )
    parser.add_argument(
        "--host", default="localhost", help="Specify which host to connect to."
    )
    parser.add_argument(
        "--port", default=None, help="Specify which port to connect to."
    )
    parser.add_argument(
        "--position", default=None, help="Specify which position to connect to."
    )
    parser.add_argument(
        "--api-token",
        default=None,
        help="Specify an API token to use, should be returned from the sequencer as a developer API token.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Specify a start date to filter results by. Format: YYYY-MM-DD",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Specify a end date to filter results by. Format: YYYY-MM-DD",
    )

    parser.add_argument(
        "output_name",
        help="Name of an output file to write csv platform qc results to.",
    )

    args = parser.parse_args()

    start_date_filter = to_datetime(args.start_date)
    end_date_filter = to_datetime(args.end_date)

    # Construct a manager using the host + port provided.
    manager = Manager(
        host=args.host, port=args.port, developer_api_token=args.api_token
    )

    # Iterate all sequencing positions:
    results = []
    found_position = False
    for pos in manager.flow_cell_positions():
        if not pos.running:
            continue

        # Ignore positions if requested:
        if args.position and args.position != pos.name:
            continue

        # Dump all pqc protocols run on the position:
        found_position = True
        pos_connection = pos.connect()
        time_filter = FilteringInfo.TimeFilter()
        if start_date_filter:
            time_filter.start_range.FromDatetime(start_date_filter)
        if end_date_filter:
            time_filter.end_range.FromDatetime(end_date_filter)
        protocols = pos_connection.protocol.list_protocol_runs(
            filter_info=FilteringInfo(
                pqc_filter=FilteringInfo.PlatformQcFilter(),
                experiment_start_time=time_filter,
            )
        )
        print(f"Searching position {pos.name} {len(protocols.run_ids)} protocols")
        for run_id in protocols.run_ids:
            # Get the detailed run info (containing device info and qc results):
            run_info = pos_connection.protocol.get_run_info(run_id=run_id)

            # Ignore the protocol if it didn't store a platform qc result:
            if run_info.pqc_result:
                results.append(
                    {
                        "passed": run_info.pqc_result.passed,
                        "total_pore_count": run_info.pqc_result.total_pore_count,
                        "position": pos.name,
                        "flow_cell_id": run_info.flow_cell.flow_cell_id
                        or run_info.flow_cell.user_specified_flow_cell_id,
                        "product_code": run_info.flow_cell.product_code
                        or run_info.flow_cell.user_specified_product_code,
                    }
                )

    with open(args.output_name, "w") as csvfile:
        result_writer = csv.DictWriter(
            csvfile,
            ["position", "flow_cell_id", "product_code", "passed", "total_pore_count"],
        )

        result_writer.writeheader()
        for result in results:
            result_writer.writerow(result)

    if not found_position and args.position:
        print(f"Failed to locate sequencing position: {args.position}")
        exit(1)


if __name__ == "__main__":
    main()
