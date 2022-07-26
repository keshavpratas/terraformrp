import argparse
import json
import os
import subprocess
import logging
from cim_functions import inventory_lookup


def run():
    target_env = parse()
    destroy(target_env)


def parse() -> dict:
    ''' ingest the destroy blob. '''
    try:
        logging.info('attempting to load blob from os environment var...')
        blob = os.environ["blob"]
    except OSError as oe:
        logging.error(f"Failed to find provisioning blob in environment vars: {oe}")
    try:
        logging.info('parsing json...')
        parsed_blob = json.loads(blob)
    except ValueError as ve:
        logging.error(f"Invalid JSON blob or failed to load JSON blob correctly {ve}")
        local_etcd.write(local_etcd_path + 'error', '10501')
        sys.exit(1)

    logging.info('pulling requisite values from blob...')
    if parsed_blob['target_env'] == 'pipeline':
        # if pipeline is passed, we must have a localfile for the environment
        json_blob = json.load(open(os.environ["localfile"]))
        target_env = json_blob['tenantmask']
    else:
        target_env = parsed_blob['target_env']
    return target_env


def destroy(target_env: dict):
    ''' destroy metadata from the environment that was checked into git'''
    # delete vars, inventory, and API data json
    try:
        data_dir = os.environ['ANSIBLE_DATA_DIR']
        job_name = os.environ['JOB_NAME']
        build_number = os.environ['BUILD_NUMBER']
    except KeyError:
        logging.error("ANSIBLE_DATA_DIR environmental variable not found")
        exit(1)
    try:
        logging.info("deleting metadata files...")
        os.chdir(f"{data_dir}")
        subprocess.run(["rm", f"vars/{target_env}.yml"])
        subprocess.run(["rm", f"inventory/{target_env}.yml"])
        subprocess.run(["rm", f"api_data/{target_env}.json"])
    except CalledProcessError as e:
        logging.error(f"failed to delete localfiles! {e}")
    try:
        subprocess.run(["git", "config", "--global", "user.email",
                       "'jnknsprd@or1010050155065.corp.adobe.com'"])
        subprocess.run(["git", "config", "--global",
                       "user.name", "'Your Obedient Servant'"])
        subprocess.run(
            ["git", "branch", "--set-upstream-to=origin/master", "master"])
        subprocess.run(["git", "pull"])
        subprocess.run(["git", "add", "-A"])
        subprocess.run(["git", "commit", "-m", f"'Auto commit of campaign-infrastructure-destruction pipeline {job_name} {build_number}'"])
        subprocess.run(["git", "push", "--set-upstream", "origin", "master"])
    except CalledProcessError as e:
        logging.error(f"failed to delete files from git! {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    run()
