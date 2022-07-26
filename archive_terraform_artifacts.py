#!/usr/bin/env python3
'''
This script copies the terraform output files to a git repo for commit.
'''

import os
import shutil
import logging

from cim_functions import get_args, inventory_lookup

def main():

    ''' main body of the script '''
    logging.basicConfig(level=logging.DEBUG)

    args = get_args()
    inventory_data = inventory_lookup(args.customer_env, args.localfile)

    src_tfvars_path = os.path.join('modules', 'variables.tf')
    src_tf_path = os.path.join('modules', 'customer.tf')
    dst_tf_path = os.path.join(os.environ['CAMP_TERRAFORM_DATA'], inventory_data['tenant_cluster_name'])

    try:
        os.makedirs(dst_tf_path, mode=0o777)
    except OSError as error:
        logging.info("TF Path %s already exists -- proceeding anyways (error=%s)", dst_tf_path, error)

    try:
        shutil.copy(src_tf_path, dst_tf_path)
        shutil.copy(src_tfvars_path, dst_tf_path)

        logging.info("Copied %s and %s to %s", src_tf_path, src_tfvars_path, dst_tf_path)

    except:
        logging.error('ERROR: Unable to copy terraform files to %s', dst_tf_path)
        exit(1)


if __name__ == "__main__":
    main()
