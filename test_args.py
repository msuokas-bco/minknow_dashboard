import sys
import collections

# Fake the classes so we can just run the logic from make_protocol_arguments
BasecallingArgs = collections.namedtuple("BasecallingArgs", ["config", "barcoding", "alignment"])
OutputArgs = collections.namedtuple("OutputArgs", ["reads_per_file"])
ReadUntilArgs = collections.namedtuple("ReadUntilArgs", ["filter_type", "reference_files", "bed_file", "first_channel", "last_channel"])

def make_protocol_arguments(
    basecalling = None,
    read_until = None,
    fastq_arguments = None,
    fast5_arguments = None,
    pod5_arguments = None,
    bam_arguments = None,
    disable_active_channel_selection = False,
    mux_scan_period = 1.5,
    args = None,
    is_flongle = False,
):
    def on_off(value):
        return "on" if value else "off"

    protocol_args = []
    if basecalling:
        protocol_args.append("--base_calling=on")
        if basecalling.config:
            protocol_args.append("--guppy_filename=" + basecalling.config)
    protocol_args.append("--fast5=" + on_off(fast5_arguments))
    if fast5_arguments:
        protocol_args.extend(["--fast5_data", "trace_table", "fastq", "raw", "vbz_compress"])
        protocol_args.append("--fast5_reads_per_file={}".format(fast5_arguments.reads_per_file))
    protocol_args.append("--pod5=" + on_off(pod5_arguments))
    if pod5_arguments:
        protocol_args.append("--pod5_reads_per_file={}".format(pod5_arguments.reads_per_file))
    protocol_args.append("--fastq=" + on_off(fastq_arguments))
    if fastq_arguments:
        protocol_args.extend(["--fastq_data", "compress"])
        protocol_args.append("--fastq_reads_per_file={}".format(fastq_arguments.reads_per_file))
    protocol_args.append("--bam=" + on_off(bam_arguments))
    if not is_flongle:
        protocol_args.append("--active_channel_selection=" + on_off(not disable_active_channel_selection))
        if not disable_active_channel_selection:
            protocol_args.append("--mux_scan_period={}".format(mux_scan_period))
    protocol_args.extend(args)
    return protocol_args

kwargs = {}
kwargs["basecalling"] = BasecallingArgs(config="dna_r10.4.1_e8.2_400bps_sup.cfg", barcoding=None, alignment=None)
out_args = OutputArgs(reads_per_file=4000)
kwargs["pod5_arguments"] = out_args
kwargs["fastq_arguments"] = out_args
kwargs["fast5_arguments"] = None

print(" ".join(make_protocol_arguments(args=[], is_flongle=False, **kwargs)))
