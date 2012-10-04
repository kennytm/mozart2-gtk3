from subprocess import check_output

def pkg_config(packages):
    """
    Return the result of `pkg-config --cflags packages`.
    """

    args = ['pkg-config', '--cflags']
    args.extend(packages)
    return check_output(args, universal_newlines=True).split()


