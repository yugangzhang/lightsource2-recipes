import sys
import traceback
import subprocess
import os
import time
import logging
import yaml
from conda_build.metadata import MetaData

def get_file_names_on_anaconda_channel(username, anaconda_cli,
                                       channel='main'):
    """Get the names of **all** the files on anaconda.org/username

    Parameters
    ----------
    username : str
    anaconda_cli : return value from binstar_client.utils.get_binstar()
    channel : str, optional
        The channel on anaconda.org/username to upload to.
        Defaults to 'main'

    Returns
    -------
    set
        The file names of all files on an anaconda channel.
        Something like 'linux-64/album-0.0.2.post0-0_g6b05c00_py27.tar.bz2'
    """
    return set([f['basename']
                for f in anaconda_cli.show_channel('main', username)['files']])


def subprocess_Popen(cmd):
    """Returns stdout and stderr

    Parameters
    ----------
    cmd : list
        List of strings to be sent to subprocess.Popen

    Returns
    -------
    stdout : """
    # capture the output with subprocess.Popen
    try:
        ret = subprocess.Popen(cmd, stderr=subprocess.PIPE,
                               stdout=subprocess.PIPE)
    except Exception as e:
        # ALL exceptions that occur in the subprocess command
        logging.error('Exception summary: %s' % e)
        logging.error('Full exception start')
        logging.error(traceback.format_exc())
        logging.error('Full exception stop')
    # decode and capture stdout and stderr
    stdout = ret.stdout.read().decode().strip()
    stderr = ret.stderr.read().decode().strip()
    return stdout, stderr

def determine_build_name(path_to_recipe, *conda_build_args):
    """Figure out what conda says the output built package name is going to be
    Parameters
    ----------
    path_to_recipe : str
        The location of the recipe on disk
    *conda_build_args : list
        List of extra arguments to be appeneded to the conda build command.
        For example, this might include ['--python', '3.4'], to tell
        conda-build to build a python 3.4 package

    Returns
    -------
    package_name : str
        Something like:
        /home/edill/mc/conda-bld/linux-64/pims-0.3.3.post0-0_g1bea480_py27.tar.bz2
    """
    conda_build_args = [] if conda_build_args is None else list(conda_build_args)
    cmd = ['conda', 'build', path_to_recipe, '--output'] + conda_build_args
    ret = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    ret = ret.decode().strip().split('\n')
    if len(ret) > 1:
        # Then this is the first time we are getting the build name and conda
        # has to check out the source. Call it a second time and you get the4
        # full path to the file that will be spit out by conda-build
        return determine_build_name(path_to_recipe, *conda_build_args)
    # we want to keep track of the exact command so we can run it later.
    # Obviously drop the `--output` flag so that conda-build actually builds
    # the package.
    cmd.remove('--output')
    return ret[0], cmd


def run_build(recipes_path, log_filename, anaconda_cli, username):
    """Build and upload packages that do not already exist at {{ username }}

    Parameters
    ----------
    recipes_path : str
        Folder where the recipes are located
    log_filename : str
        Filename to log to
    anaconda_cli : return value from binstar_client.utils.get_binstar()
    username : str
        The anaconda user to upload all the built packages to
    """
    FORMAT = "%(levelname)s | %(asctime)-15s | %(message)s"
    logging.basicConfig(filename=log_filename, level=logging.DEBUG,
                        format=FORMAT)


    # figure out build names
    build_names = []
    logging.info("Determining package build names...")
    for folder in sorted(os.listdir(recipes_path))[:1]:
        recipe_dir = os.path.join(recipes_path, folder)
        for pyver in ['2.7', '3.4', '3.5']:
            path_to_built_package, build_cmd = determine_build_name(
                recipe_dir, '--python', pyver)
            name_on_anaconda = os.sep.join(
                path_to_built_package.split(os.sep)[-2:])
            meta = MetaData(recipe_dir)
            logging.info(name_on_anaconda)
            build_names.append((path_to_built_package, name_on_anaconda,
                                build_cmd, meta))
    # check anaconda to see if they already exist
    lightsource2_packages = get_file_names_on_anaconda_channel(
        'lightsource2-dev', anaconda_cli)

    # split into 'already_exist' and 'need_to_build'
    build_package = []
    dont_build_package = []
    for full_path, name, build_cmd, metadata in build_names:
        if name in lightsource2_packages:
            dont_build_package.append((name, build_cmd))
        else:
            build_package.append((name, build_cmd))

    # log the names of those that already exist
    logging.info("%s / %s packages already exist on %s" % (
                len(dont_build_package),
                len(dont_build_package) + len(build_package),
                username))
    if dont_build_package:
        logging.info(dont_build_package)
    else:
        logging.info("No packages exist on %s" % username)

    # log the names of those that need to build
    logging.info("%s / %s packages do not exist on %s" % (
                len(build_package),
                len(dont_build_package) + len(build_package),
                username))
    if build_package:
        logging.info(build_package)
    else:
        logging.info("No packages to be built.")

    # build all the packages that need to be built

    TOKEN = os.environ.get("BINSTAR_TOKEN", None)
    UPLOAD_CMD = ['anaconda', '-t', TOKEN, 'upload', '-u',
                  username]
    # for each package
    for full_path, pkg_name, cmd, metadata in build_names:
        # output the package build name
        logging.info("Building: %s"% pkg_name)
        # output the build command
        logging.info("Build cmd: %s" % cmd)
        stdout, stderr = subprocess_Popen(cmd)
        # log stdout as 'info'
        logging.info('STDOUT')
        logging.info(stdout)
        # log stderr as 'error'
        logging.info('STDERR')
        logging.error(stderr)
        # upload the package
        logging.info("UPLOAD START")
        if TOKEN is None:
            logging.error("BINSTAR_TOKEN env var not set. Can't upload!")
        else:
            stdout, stderr = subprocess_Popen(UPLOAD_CMD + [full_path])
            logging.info("STDOUT")
            logging.info(stdout)
            logging.info("STDERR")
            logging.info(stderr)


def set_binstar_upload(on=False):
    """Turn on or off binstar uploading

    Parameters
    ----------
    on : bool, optional
        True: turn on binstar uploading
        False: turn off binstar uploading
        Defaults to False

    Raises exception if disabling binstar upload fails
    """
    rcpath = os.path.join(os.path.expanduser('~'), '.condarc')
    with open(rcpath, 'r') as f:
        rc = yaml.load(f.read())
    binstar_upload = rc.get('binstar_upload', False)
    if binstar_upload != on:
        rc['binstar_upload'] = on
        with open(rcpath, 'w') as f:
            # write the new yaml in `rcpath`
            f.write(yaml.dumps(rc))


if __name__ == "__main__":
    def print_usage():
        print("\nUsage:\n\tpython dev-build.py /path/to/dev/recipes")

    args = sys.argv
    if len(args) != 2:
        print("Error!")
        print("The command \"%s\" is invalid" % ' '.join(args))
        print("You supplied %s arguments. I am expecting 2." % len(args))
        print_usage()
        sys.exit(2)

    recipes_path = args[1]
    if not os.path.exists(recipes_path):
        print("Error!")
        print("The path '%s' does not exist." % recipes_path)
        print("Please supply the path to the dev recipes as the first "
              "argument to dev-build.py")
        print_usage()
        sys.exit(3)

    # just disable binstar uploading whenever this script is running.
    print('Disabling binstar upload. If you want to turn it back on, '
          'execute: `conda config --set binstar_upload true`')
    set_binstar_upload(True)

    # set up logging
    full_recipes_path = os.path.abspath(recipes_path)
    log_dirname = os.path.join(os.path.expanduser('~'),
                                  'auto-build-logs', 'dev')
    os.makedirs(log_dirname, exist_ok=True)
    log_filename = time.strftime("%m.%d-%H.%M")
    dev_log = os.path.join(log_dirname, log_filename)
    print('Logging output to %s' % dev_log)

    # create the anaconda cli
    import binstar_client
    from binstar_client import Binstar
    from argparse import Namespace
    token = os.environ.get('BINSTAR_TOKEN', None)
    at_nsls2 = True
    try:
        ret = subprocess.call(['ping', 'pergamon', '-c', '5'], timeout=1).decode().strip()
        if 'unknown host' in ret:
            at_nsls2 = False
    except subprocess.TimeoutExpired:
        # we are probably not at nsls2
        at_nsls2 = False

    if at_nsls2:
        # Fill in your binstar token here
        username = 'nsls2-tag'
        site = 'https://pergamon.cs.nsls2.local:8443/api'
        os.environ['REQUESTS_CA_BUNDLE'] = '/etc/certificates/ca_cs_nsls2_local.crt'
    else:
        username = 'lightsource2-dev'
        site = None

    anaconda_cli = binstar_client.utils.get_binstar(Namespace(token=token,
                                                              site=site))
    try:
        run_build(full_recipes_path, dev_log, anaconda_cli, username)
    except Exception as e:
        logging.error("Error in run_build!")
        logging.error(e)
        logging.error("Full stack trace")
        logging.error(traceback.format_exc())

    if at_nsls2:
        del os.environ['REQUESTS_CA_BUNDLE']
