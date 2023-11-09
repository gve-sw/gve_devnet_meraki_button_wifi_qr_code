#!/usr/bin/env python3
"""
Copyright (c) 2023 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Trevor Maco <tmaco@cisco.com>"
__copyright__ = "Copyright (c) 2023 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

import datetime
import os
import requests
import secrets
import string
import sys

import meraki
import wifi_qrcode_generator as qr
from dotenv import load_dotenv
from flask import Flask, request, render_template, redirect, url_for
from rich.console import Console
from rich.panel import Panel

import config

# Load ENV Variable
load_dotenv()
MERAKI_API_KEY = os.getenv("MERAKI_API_KEY")
SHARED_SECRET = os.getenv("SHARED_SECRET")
ORG_NAME = os.getenv("ORG_NAME")
NETWORK_NAME = os.getenv("NETWORK_NAME")
SSID_NAME = os.getenv("SSID_NAME")

# Flask and Meraki
app = Flask(__name__)
dashboard = meraki.DashboardAPI(api_key=MERAKI_API_KEY, suppress_logging=True)

# Global variables
network_id = ''
ssid_details = {}
existing_password = ''

# Rich Console Instance
console = Console()


# Methods
def getSystemTimeAndLocation():
    """Returns location and time of accessing device"""
    # request user ip
    userIPRequest = requests.get('https://get.geojs.io/v1/ip.json')
    userIP = userIPRequest.json()['ip']

    # request geo information based on ip
    geoRequestURL = 'https://get.geojs.io/v1/ip/geo/' + userIP + '.json'
    geoRequest = requests.get(geoRequestURL)
    geoData = geoRequest.json()

    # create info string
    location = geoData['country']
    timezone = geoData['timezone']
    current_time = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")
    timeAndLocation = "System Information: {}, {} (Timezone: {})".format(location, current_time, timezone)

    return timeAndLocation


def get_network_id(org_name, network_name):
    """
    Get network ID that contains SSID
    :param org_name: Org Name
    :param network_name: Network Name
    :return: Network ID
    """
    # Get Meraki Org ID
    orgs = dashboard.organizations.getOrganizations()
    org_id = ''
    for org in orgs:
        if org['name'] == org_name:
            org_id = org['id']
            break

    if org_id == '':
        return None

    # Get Meraki Network ID
    networks = dashboard.organizations.getOrganizationNetworks(organizationId=org_id)
    net_id = ''
    for network in networks:
        if network['name'] == network_name:
            net_id = network['id']
            break

    if net_id == '':
        return None

    return net_id


def get_ssid_details(ssid_name):
    """
    Query SSID details, change PSK for SSID
    :param ssid_name: SSID Name
    :return: SSID information
    """

    # Get SSID Information
    ssids = dashboard.wireless.getNetworkWirelessSsids(networkId=network_id)
    target_ssid = {}
    for ssid in ssids:
        if ssid['name'] == ssid_name:
            target_ssid = ssid
            break

    if target_ssid == {}:
        return None

    return target_ssid


def random_ssid_passcode(ssid_number):
    """
    Change PSK of Meraki Wi-Fi network to randomly generated 12 character PSK
    :param ssid_number: SSID identifier
    :return: New PSK
    """

    # Generate random Wi-Fi password
    random_psk = (
        "".join((secrets.choice(string.ascii_letters + string.digits) for i in range(12)))
    )

    # Update SSID with new password
    dashboard.wireless.updateNetworkWirelessSsid(networkId=network_id, number=ssid_number, psk=random_psk)

    return random_psk


def select_from_list_ssid_passcode(ssid_number):
    """
    Change PSK of Meraki Wi-Fi network to randomly selected PSK from PASSWORD_LIST
    :param ssid_number: SSID identifier
    :return: New PSK
    """

    # Randomly select Wi-Fi password from PASSWORD_LIST
    random_psk = secrets.choice(config.PASSWORD_LIST)

    # Update SSID with new password
    dashboard.wireless.updateNetworkWirelessSsid(networkId=network_id, number=ssid_number, psk=random_psk)

    return random_psk


def generate_qr_code(target_ssid):
    """
    Generate a QR code for the Meraki Wi-Fi Network. Only Open and PSK (WPA, WPA2, WEP) supported!
    :param target_ssid: SSID details (PSK, Name, Number, etc.)
    :return:
    """
    if not os.path.exists("./static/qr_codes/"):
        os.makedirs("./static/qr_codes/")

    # Check if ssid uses a support authentication method
    auth_mode = target_ssid["authMode"]
    if auth_mode not in ("open", "psk"):
        console.print(f"[red]{auth_mode}[/] is currently not supported by this script.")
        return None

    # Use wifi_qrcode() to create a QR image
    ssid = target_ssid['name']
    hidden = not target_ssid['visible']

    # Encryption type (note: WPA, WEP, Open supported)
    encryption_type = target_ssid.get('encryptionMode', 'open').upper()
    psk = target_ssid.get("psk", None)

    if encryption_type in ("WPA", "WEP"):
        qr_code = qr.wifi_qrcode(ssid, hidden, encryption_type, psk)
    elif encryption_type == 'OPEN':
        qr_code = qr.wifi_qrcode(ssid, hidden, 'nopass', None)
    else:
        console.print(f"[red]{encryption_type}[/] is currently not supported by this script.")
        return None

    # Save the qr image
    qr_code.make_image().save(f'./static/qr_codes/{ssid}.png')

    return qr_code


# Flask Routes
@app.route('/')
def index():
    console.print(Panel.fit("SSID Details:"))
    console.print(ssid_details)

    ssid_name = ssid_details['name']
    ssid_password = ssid_details.get("psk", 'N/A (Open)')

    # Check if QR code exists for SSID
    qr_exists = False
    if os.path.exists(f'static/qr_codes/{ssid_name}.png'):
        qr_exists = True

    # Check if SSID disabled
    qr_disabled = False
    if not ssid_details['enabled']:
        qr_disabled = True

    return render_template('index.html', hiddenLinks=False, timeAndLocation=getSystemTimeAndLocation(),
                           ssid_name=ssid_name, ssid_password=ssid_password, qr_exists=qr_exists,
                           qr_disabled=qr_disabled)


@app.route('/button-press', methods=["GET", "POST"])
def button_press():
    global ssid_details
    if request.method == "POST":
        # Check Shared Secret (validate webhook request is legit)
        if 'sharedSecret' in request.json and request.json['sharedSecret'] != SHARED_SECRET:
            return 'Error: Invalid secret, discarding webhook request'

        console.print(f"POST request received from [blue]{request.json['deviceName']}[/]")

        try:
            message = request.json['alertData']['message']
            button_press_type = request.json['alertData']['trigger']['button']['pressType']
        except KeyError:
            console.print(f'[red]Error:[/] Fields missing from button webhook request, please ensure correct correct '
                          f'Meraki webhook is in use.')
            return f'[red]Error:[/] Fields missing from button webhook request, please ensure correct correct Meraki ' \
                   f'webhook is in use. '

        # Either button press is fine
        if button_press_type == 'short' or button_press_type == 'long':
            console.print(f'Button press type: {button_press_type}')

            # Get SSID Information
            new_ssid_details = get_ssid_details(SSID_NAME)

            if new_ssid_details is None:
                console.print(f'[red]Error:[/] {SSID_NAME} not found..')
                return f'Error: {SSID_NAME} not found...'

            console.print(f'Found SSID [green]{SSID_NAME}[/]')

            console.print(Panel.fit("SSID Details:"))
            console.print(new_ssid_details)

            # Sanity check SSID is enabled from button press
            if new_ssid_details['enabled']:
                # Change SSID Password (if authMode is psk, ignore if 'open' or something else)
                if new_ssid_details['authMode'] == 'psk':

                    # If Password Policy is 1, use existing password
                    if config.PASSWORD_POLICY == 1:
                        new_ssid_details['psk'] = existing_password
                        console.print(f'Password kept the same: [green]{new_ssid_details["psk"]}[/]')
                    # If Password Policy is 2, use random password
                    elif config.PASSWORD_POLICY == 2:
                        new_ssid_details['psk'] = random_ssid_passcode(new_ssid_details['number'])
                        console.print(f'Password changed to [green]{new_ssid_details["psk"]}[/]')
                    # Password Policy is 3, randomly select from Password List
                    else:
                        new_ssid_details['psk'] = select_from_list_ssid_passcode(new_ssid_details['number'])
                        console.print(f'Password changed to [green]{new_ssid_details["psk"]}[/], selected from PASSWORD_LIST')

                # Generate QR code for SSID
                status = generate_qr_code(new_ssid_details)

                if not status:
                    console.print("[red]Error:[/] QR Code Creation failed...")
                else:
                    console.print(f'QR Code Created for {SSID_NAME}!')

            else:
                console.print('SSID is disabled! No new QR Code generated.')

            ssid_details = new_ssid_details
            return message

    else:
        console.print(f'Received {request.method} request... redirecting to home')
        return redirect(url_for('index'))


# Set network id and initial SSID information before running app (avoid unnecessary API calls)
console.print(Panel.fit(f"Getting Network ID for {NETWORK_NAME}",
                        title="Step 1"))

# Get Meraki Network ID for SSID Network (run once)
network_id = get_network_id(ORG_NAME, NETWORK_NAME)

if not network_id:
    console.print(f'[red]Error:[/] {NETWORK_NAME} not found.. Exiting.')
    sys.exit(-1)
console.print("[green]Found Network ID![/]")

console.print(Panel.fit(f"Getting SSID information for {SSID_NAME}",
                        title="Step 2"))
# Get SSID Information
ssid_details = get_ssid_details(SSID_NAME)

if ssid_details is None:
    console.print(f'[red]Error:[/] {SSID_NAME} not found..')
    sys.exit(-1)

# Password Policy sanity check
if config.PASSWORD_POLICY not in [1, 2, 3]:
    console.print(f'[red]Error:[/] PASSWORD_POLICY of {config.PASSWORD_POLICY} is an invalid choice!')
    sys.exit(-1)
elif config.PASSWORD_POLICY == 3 and len(config.PASSWORD_LIST) == 0:
    console.print(f'[red]Error:[/] PASSWORD_POLICY of {config.PASSWORD_POLICY} selected but PASSWORD_LIST is empty!')
    sys.exit(-1)

# If Password Policy 1 selected (same password) -> store password in global variable
if config.PASSWORD_POLICY == 1 and ssid_details['authMode'] == 'psk':
    existing_password = ssid_details['psk']

console.print(Panel.fit(f"Starting Flask App...", title="Step 3"))

if __name__ == '__main__':
    app.run(port=5000)
