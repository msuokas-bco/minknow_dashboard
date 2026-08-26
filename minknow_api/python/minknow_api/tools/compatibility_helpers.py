import importlib.resources


def read_binary_resource(package, file):
    """Compatibility function reading a binary resource with a python package"""
    try:
        return (importlib.resources.files(package) / file).read_bytes()
    except AttributeError:
        return importlib.resources.read_binary(package, file)
