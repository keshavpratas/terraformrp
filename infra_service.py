#!/usr/bin/env python3
'''
Create, alter and destroy Azure resources.
'''

import os
import logging
import argparse
import io
import re
import time

from python_terraform import *

# pylint: disable=logging-fstring-interpolation,line-too-long,anomalous-backslash-in-string,no-else-return

# placeholder codes are temporary. real codes will be put in when we build the standalone microservice.
# Jenkins has no way to raise these today, so they have no actual value.

exit_codes = {
    "SUCCESS": 10000,
    "PLUGIN_ERROR": 10001,
    "APPLY_NOT_SPECIFIED": 10003,
    "UNKNOWN_RESOURCE": 10004,
    "GENERIC_FAILURE": 10005,
    "I_HAVE_NO_CLUE": 10006,
    "RETRYABLE_ERROR": 10007,
    "VM_CORE_QUOTA": 10008
}

def get_args():
    ''' process commandline arguments '''
    parser = argparse.ArgumentParser(
                description='Get Command line arguments for infrastructure management tool')
    parser.add_argument('--destroy', dest='action_destroy', action='store_true',
                        default=False, help='Execute a destroy action')
    parser.add_argument('--apply', dest='action_apply', action='store_true',
                        default=False, help='Actually do the work')

    return parser.parse_args()


def log_review(log_capture_string):
    ''' Parse the log output and match known patterns '''

    # Logging module has been configured to capture the output to a string, rather than
    # print it. Here we will try to do something useful with that data.
    #
    # a side effect is that we have to use print() for on screen output.
    log_contents = log_capture_string.getvalue()

    # The log is saved as a multi-line string. Break it into multiple lines for ease
    # of parsing.

    log_lines = log_contents.splitlines()
    # Start off with no detailed output and a really bonkers error code, just so we don't
    # fail due to undefined vars.
    detailed_output = False
    return_code = exit_codes['I_HAVE_NO_CLUE']

    # This list defines the retryable errors we want to capture.
    # They must be in the form of a re.search regexp:
    # - whitespace escaped
    # .* before and after to allow them to appear anywhere in the string

    retryable_errors = [
        '.*RetryableError.*',
        '.*context\s+deadline\s+exceeded.*'
    ]

    retryable_regexp = '(?:% s)' % '|'.join(retryable_errors) 

    # Since the end of the log is the most meaningful, start from the end.
    for line in reversed(log_lines):

        # This is the standard "create succeeded" message from terraform
        if re.match("Apply complete!", line):
            print(line, flush=True)
            return_code = exit_codes['SUCCESS']
            break

        # For destroys, this is the expected success message
        elif re.match("Destroy complete!", line) or re.match("Destruction complete", line):
            print(line, flush=True)
            return_code = exit_codes['SUCCESS']
            break

        # There isn't a single consistent way to tell whether an error can be retried or not. This is
        # something we will build up over time. The key here is that if terraform returns retryable_error,
        # this wrapper will attempt to run terraform a second time before bailing out completely. It's not
        # much reliency but it's something.

        elif re.search(retryable_regexp, line):
            return_code = exit_codes['RETRYABLE_ERROR']
            detailed_output = True
            break

        # Some, not all, errors start with Error:
        elif re.match("Error:", line):
            # this error happens when the terraform config specifies an invalid plugin configuration
            if re.search('error\s+satisfying\s+plugin\s+requirements', line):
                return_code = exit_codes['PLUGIN_ERROR']
                print(f"Terraform plugin configuration invalid {return_code}", flush=True)
                detailed_output = True
                break

            # VM cores quota exceeded
            elif re.search('exceeding\s+approved\s+Total\s+Regional\s+Cores\s+quota', line):
                return_code = exit_codes['VM_CORE_QUOTA']
                print(f"VM Core quota exceeded. Microsoft support ticket required. {return_code}", flush=True)
                detailed_output = True
                break

            # this happens if you try to use a terraform resource that doesn't exist.
            elif re.search('unknown\s+resource', line):
                return_code = exit_codes['UNKNOWN_RESOURCE']
                print(f"Terraform unknown resource error {return_code}", flush=True)
                detailed_output = True
                break

            # This one is "something failed but I don't know what"
            else:
                return_code = exit_codes['GENERIC_FAILURE']
                print(f"Terraform unhandled exception {return_code}", flush=True)
                detailed_output = True
                break

    # If we get some sort of failure, print the entire error message to screen in the most
    # human readable format we can.
    if detailed_output:
        print(" ", flush=True)
        print("An execution error occurred. Detailed output:", flush=True)
        print("------------------------------------------------------", flush=True)
        for line in log_lines:
            line = line.strip()
            if len(line) > 1 and not re.search('Refreshing\s+state', line):
                print(line, flush=True)
        print("------------------------------------------------------", flush=True)

    return return_code


def tf_apply(terra, logger, log_capture_string, apply, destroy):
    ''' Execute terraform plan/apply for an azure environment '''

    # This is used to print readable output further down.
    if destroy:
        action_string = 'destroy'
    else:
        action_string = 'create'

    # See? Told you.
    print(f"Executing terraform {action_string} plan", flush=True)

    # Actually execute terraform
    plan_code, plan_stdout, plan_stderr = terra.plan(destroy=destroy)

    # Feed stdout / stderr to logging module.
    logger.info(plan_stdout)
    logger.error(plan_stderr)

    # Assume that apply was NOT set.
    skip_apply = False

    # Plan will return 0 or 2 as success codes, depending on whether changes are needed or not.
    # any other code is a failure.
    if plan_code in [0, 2]:

        # Since the plan worked, lets dig out the lines we care about.
        terra_plan = plan_stdout.splitlines()

        for line in terra_plan:
            line = line.strip()
            # Don't display empty lines (there are a lot) or refreshing state info
            if len(line) > 1 and not re.search('Refreshing\s+state', line):

                # The line that starts with Plan: is where it tells you what it's going to do.
                if re.search('Plan:', line):
                    # TODO: add logic here for unexpected changes or destroys. Not in scope today.
                    print(line, flush=True)
                elif re.search('No changes. Infrastructure is up-to-date', line):
                    # If terraform plan says no changes are needed, skipp apply even if --apply is passed
                    skip_apply = True
                elif destroy:
                    # On destroy only, print the entire output so that we get solid confirmation EXACTLY what will be destroyed.
                    print(line, flush=True)

    else:
        # If the plan failed to execute, that's usually a syntax issue.
        exit_handler = log_review(log_capture_string)
        print(f"Plan failed with error {exit_handler}", flush=True)
        return exit_handler

    if apply:
        # If the plan has no action, skip the apply and return success
        if skip_apply:
            print("Plan determined that no action was needed. Skipping apply", flush=True)
            return exit_codes['SUCCESS']

        # Give the operator 30 seconds to abort if the destroy plan looks bad.
        if destroy:
            print("Pausing for 30 seconds before destroying existing infrastructure.", flush=True)
            time.sleep(30)

        # Let the operator know that things are going to be quiet for a bit.
        print(f"Starting terraform {action_string}. There will be little to no output for the next 15 - 20+ minutes.", flush=True)

        # Retryable errors are common. This is a simple loop to try again if it fails. Counting from one because humans.
        count = 1
        max_retries = 3
        exit_handler = exit_codes['RETRYABLE_ERROR']

        while count < max_retries and exit_handler == exit_codes['RETRYABLE_ERROR']:

            print(f"Terraform apply attempt {count} starting", flush=True)

            if destroy:
                return_code, stdout, stderr = terra.destroy(auto_approve=True)
            else:
                return_code, stdout, stderr = terra.apply(skip_plan=True)

            logger.info(stdout)
            logger.error(stderr)

            exit_handler = log_review(log_capture_string)

            count += 1

        return exit_handler
    else:
        print("Argument --apply not specified. No action taken", flush=True)
        return exit_codes['APPLY_NOT_SPECIFIED']


def main():
    ''' main body of the script '''

    logger = logging.getLogger('basic_logger')
    logger.setLevel(logging.DEBUG)

    log_capture_string = io.StringIO()
    capture_handle = logging.StreamHandler(log_capture_string)
    capture_handle.setLevel(logging.DEBUG)

    logger.addHandler(capture_handle)

    os.chdir("modules")
    terra = Terraform(terraform_bin_path="/usr/local/bin/terraform-v12")
    terra.init()

    args = get_args()
    tf_exit_code = tf_apply(terra, logger, log_capture_string,
                            args.action_apply, args.action_destroy)
    print(f"Infra service returned {tf_exit_code}", flush=True)

    if tf_exit_code == exit_codes['SUCCESS']:
        exit(0)
    else:
        exit(1)

    log_capture_string.close()


if __name__ == "__main__":
    main()
