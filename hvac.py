import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import hvac
import logging
import os
import argparse
import yaml 
import json

def run():
    try:
        args = get_args()
        api_data = inventory_lookup(args.customer_env, args.localfile)
        if api_data.get('product') == '6' or api_data.get('product') == '7':
            return
        connect_vault()
        #setup_webdriver()
        check_login_success(api_data)
    except Exception as e:
        print("ERROR: Testing failed! {}".format(e))
        failure(args.fail_hard)

# This is copy-pasted from another script. Since the plan is for this to be a standalone project, I didn't want to use a shared
# library at this point. 

def get_args():
    ''' process commandline arguments '''
    parser = argparse.ArgumentParser(
        description='Get Command line arguments for full inventory generator')
    parser.add_argument('--customer-env', dest='customer_env', action='store', required=True,
                        help='Full path to ansible vars file')
    parser.add_argument('--localfile', dest='localfile', action='store',
                        required=False, help='Path to local json file')
    parser.add_argument('--fail-hard', dest='fail_hard', action='store_true', default=False,
                        help='If you pass this arg, the script will exit 1 if the test fails')
    return parser.parse_args()

def inventory_lookup(customer_env, localfile=None):
    ''' Look up the campaign instance in the inventory service '''

    if customer_env == 'pipeline':
        # In this mock case, we are going to use the API response file generated by
        # the legacy pipeline service.

        if localfile is None:
            logging.error("When using --customer-env pipeline, you must also provide --localfile")
            exit(1)

        if os.path.isfile(localfile):
            try:
                with open(localfile) as api_json:
                    return json.load(api_json)

            except Exception as error_code:
                logging.error("Unable to load the JSON data. %s", error_code)
                exit(1)
        else:
            logging.error("%s does not exist", localfile)
            exit(1)
    else:
        # Like so much of this script, this is a workaround for the lack of an API endpoint. 
        try:
            ansible_data_dir=os.environ['ANSIBLE_DATA_DIR']
        except KeyError as e:
            logging.error("ANSIBLE_DATA_DIR environmental variable not found")
            exit(1)

        inventory_file = "{}.yml".format(customer_env)
        inventory_path = os.path.join(ansible_data_dir, "vars", inventory_file)

        api_data = {}

        if os.path.exists(inventory_path):
            with open(inventory_path, 'r') as inventory_handle:
                api_data = yaml.load(inventory_handle)

                api_data['tenanturl'] = api_data['campaign_url']

                return api_data
        else:
            logging.error("%s not found in %s", inventory_file, ansible_data_dir)
            exit(1)

def failure(fail_hard):
    if fail_hard == True:
        exit(1)
    else:
        exit(0)

def connect_vault():
    global vault
    adobe_vault_url = ''
    try:
        vault = hvac.Client(adobe_vault_url)
        print('INFO: Established connection to CST Vault')
    except Exception as error:
        print('ERROR: Vault connection failed. Maybe the token is expired?')
        print(error)
        exit(1)

    if 'VAULT_TOKEN' in os.environ:
        vault.token = os.environ['VAULT_TOKEN']
    else:
        print("ERROR: VAULT_TOKEN environment variable not set. Exiting.")
        exit(1)

def setup_webdriver():
    global driver
    #chrome_options = Options()
    #chrome_options.add_argument('--headless')
    #chrome_options.add_argument('--no-sandbox')
    #chrome_options.add_argument('--disable-dev-shm-usage')
    try:
        #driver = webdriver.Chrome('/usr/local/bin/chromedriver',chrome_options=chrome_options)
        driver = webdriver.Chrome()
    except Exception as e:
        print ("err==>>",e)
        #print("Failed to initialize selenium webdriver! Are the selenium driver and Chrome properly installed?")

def login(instance_url, username, password):
    driver = None
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    try:
        driver = webdriver.Chrome('/usr/local/bin/chromedriver', chrome_options=chrome_options)
    except Exception as e:
        print ("err==>>",e)
        #print("Failed to initialize selenium webdriver! Are the selenium driver and Chrome properly installed?")
    
    login_url = instance_url + "/xtk/logon.jssp?ims=0"
    print("connecting to {}".format(login_url))
    driver.get(login_url)
    time.sleep(3) # Let the user actually see something!
    login_box = driver.find_element_by_css_selector('#username')
    login_box.send_keys(username)
    password_box = driver.find_element_by_css_selector('#password')
    password_box.send_keys(password)
    password_box.submit()
    time.sleep(4) # Let the user actually see something!

def check_element_exists(element):
    try:
        driver.find_element_by_css_selector(element)
        return True
    except Exception as e:
        print(e)
        return False

def check_for_text(text):
    try:
        if (text in driver.page_source):
            return True
        else:
            return False
    except Exception as e:
        print("failed to find text on page! {}".format(e))

# Log in and ensure that the UI is loaded
def check_login_success(vars_data):
    camp_instance_url = vars_data['tenanturl']
    vault_secret_path = vars_data['vault_secret_path']
    admin_username = 'admin'
    admin_password = vault.read(vault_secret_path)['data']['admin']

    try:
        login(camp_instance_url, admin_username, admin_password)
        if check_element_exists('#') or check_for_text('Your instance has been upgraded to repo'):
            print("Login successful!")
            driver.quit()
            exit(0)
        else:
            print("Login failed!")
            print("Selenium test failure! Is the campaign application running?")
            driver.quit()
            failure(args.fail_hard)

    except Exception as e:
        print("login test failed! {}".format(e))
        driver.quit()
        failure(args.fail_hard)

if __name__ == "__main__":
    run()
