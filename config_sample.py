# Password methodology choice. Only applicable to SSIDs that use PSK. See Available options:
# 1. Same Password (set originally in Meraki Dashboard) -> Default Option
# 2. Random Password (Randomly generate password)
# 3. Password List (Randomly select from PASSWORD_LIST - must have at least 1 password in list, passwords must
# conform to Meraki SSID password policy: >= 8 alphanumeric characters, etc.)
PASSWORD_POLICY = 1
PASSWORD_LIST = ['sample1', 'sample2']