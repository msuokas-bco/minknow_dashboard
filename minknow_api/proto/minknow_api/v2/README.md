This section of the API is an under-construction replacement of the per-flow-cell-position APIs.

The calls should be made to the usual manager port (9501/2) rather than to individual `control_server` ports.
Calls will be modified to add a `run_id` field, or potentially a 'repeated' `run_id` for interacting with multiple protocols simultaneously.
