import datetime
import os
import requests
import secrets
import string
import sys

import meraki
import wifi_qrcode_generator as qr
from flask import Flask, request, render_template, redirect, url_for
from rich.console import Console
from rich.panel import Panel

from config import *

# Flask and Meraki
app = Flask(__name__)
dashboard = meraki.DashboardAPI(api_key=MERAKI_API_KEY, suppress_logging=True)

# Global variables
NETWORK_ID = ''
ssid_details = {}

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


def get_ssid_details(network_id, ssid_name):
    """
    Query SSID details, change PSK for SSID
    :param org_name: Organization Name
    :param network_name: Network Name
    :param ssid_name: SSID Name
    :return: SSID information
    """

    # Get SSID Information
    ssids = dashboard.wireless.getNetworkWirelessSsids(networkId=network_id)
    ssid_details = {}
    for ssid in ssids:
        if ssid['name'] == ssid_name:
            ssid_details = ssid
            break

    if ssid_details == {}:
        return None

    return ssid_details


def change_ssid_passcode(net_id, ssid_number):
    """
    Change PSK of Meraki Wi-Fi network to randomly generated 12 character PSK
    :param net_id: Network ID
    :param ssid_number: SSID identifier
    :return: New PSK
    """
    global ssid_password

    # Generate random Wi-Fi password
    random_psk = (
        "".join((secrets.choice(string.ascii_letters + string.digits) for i in range(12)))
    )

    # Update SSID with new password
    dashboard.wireless.updateNetworkWirelessSsid(networkId=net_id, number=ssid_number, psk=random_psk)

    return random_psk


def generate_qr_code(ssid_details):
    """
    Generate a QR code for the Meraki Wi-Fi Network. Only Open and PSK (WPA, WPA2, WEP) supported!
    :param ssid_details: SSID details (PSK, Name, Number, etc.)
    :return:
    """
    if not os.path.exists("./static/qr_codes/"):
        os.makedirs("./static/qr_codes/")

    # Check if ssid uses a support authentication method
    auth_mode = ssid_details["authMode"]
    if auth_mode not in ("open", "psk"):
        console.print(f"[red]{auth_mode}[/] is currently not supported by this script.")
        return None

    # Use wifi_qrcode() to create a QR image
    ssid = ssid_details['name']
    hidden = not ssid_details['visible']

    # Encryption type (note: WPA, WEP, Open supported)
    encryption_type = ssid_details.get('encryptionMode', 'open').upper()
    psk = ssid_details.get("psk", None)

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
            new_ssid_details = get_ssid_details(NETWORK_ID, SSID_NAME)

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
                    new_ssid_details['psk'] = change_ssid_passcode(NETWORK_ID, new_ssid_details['number'])
                    console.print(f'Password changed to [green]{new_ssid_details["psk"]}[/]')

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
            console.print('TESTS MERAKI DASHBOARD WEBHOOK')
            return 'Meraki Button - Webhook Test'

    else:
        console.print(f'Received {request.method} request... redirecting to home')
        return redirect(url_for('index'))


if __name__ == '__main__':
    console.print(Panel.fit(f"Getting Network ID for {NETWORK_NAME}",
                            title="Step 1"))

    # Get Meraki Network ID for SSID Network (run once)
    NETWORK_ID = get_network_id(ORG_NAME, NETWORK_NAME)

    if not NETWORK_ID:
        console.print(f'[red]Error:[/] {NETWORK_NAME} not found.. Exiting.')
        sys.exit(-1)
    console.print("[green]Found Network ID![/]")

    console.print(Panel.fit(f"Getting SSID information for {SSID_NAME}",
                            title="Step 2"))
    # Get SSID Information
    ssid_details = get_ssid_details(NETWORK_ID, SSID_NAME)

    if ssid_details is None:
        console.print(f'[red]Error:[/] {SSID_NAME} not found..')
        sys.exit(-1)
    console.print(Panel.fit(f"Starting Flask App...",
                            title="Step 3"))
    app.run(port=8080)
