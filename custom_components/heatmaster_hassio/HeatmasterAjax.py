import binascii
import logging
from xml.dom.minidom import parseString
import requests


class HeatmasterAjax():
    """
    Heatmaster class uses the AJAX url to communicate and fetch data from the simens LOGO8
    """
    auth_cookie = None

    def __init__(self,
                 ip_address: str,
                 username: str = "Web User",
                 password: str = "heatmaster",
                 no_login: bool = False) -> None:
        """
        Creates a new HeatmasterAjax object.

        ip_address: The IP of the heatmaster furnace
        username: The username of the LOGO console, DEFAULT: "Web User"
        password: The password of the LOGO console, DEFAULT: "heatmaster"
        no_login: Set this flag if you dont want the contructor to login for you
        """
        self.ip_address = ip_address
        self.url = f"http://{ip_address}/AJAX"
        self.username = username
        self.password = password
        self.status = 1
        if not no_login:
            self.login()

    def login(self) -> None:
        """
        Log into the Heatmaster LOGO8 console
        """
        #calls the challange command with 1,2,3,4 as the key (Same key as UI)
        login1 = requests.post(self.url, data="UAMCHAL:3,4,1,2,3,4",
                               timeout=30)
        #split the response into temporary sec cookie and the challenge key
        login1_keys = login1.text.split(',')

        #generate the server and password challenge responses
        p_chal = self._generate_password_challenge(int(login1_keys[2]))
        s_chal = self._generate_server_challenge(int(login1_keys[2]))
        #Create the payload for the challenge response
        challenge_data = f"UAMLOGIN:{self.username},{p_chal},{s_chal}"

        login2 = requests.post(self.url,
                               data=challenge_data,
                               cookies={"Security-Hint": login1_keys[1]},
                               timeout=30)
        self.auth_cookie = {"Security-Hint": login2.text.split(',')[1]}

    def _generate_server_challenge(self,
                                   server_key: int) -> int:
        """
        Generates the server challenge key for the login process.

        server_key: The challenge key from the server
        """
        #The server challenge is just the 4 keys and the challenge key xor'd
        return 1 ^ 2 ^ 3 ^ 4 ^ server_key

    def _generate_password_challenge(self,
                                     server_key: int) -> int:
        """
        Generates a password challenge for the login process    

        server_key: The challenge key from the server
        """
        #the password string is simple, server key string appended to the pass
        password_string = f"{self.password}+{server_key}"
        #Generate a CRC hash of the password string
        crc = binascii.crc32(bytes(password_string, "utf8"))
        #xor the CRC result with the server_key
        return crc ^ server_key

    def _set_status(self,
                    status_text: list):
        """
        Sets the status of the server based on the XML data. 

        status_text: XML data
        """
        for item in status_text:
            item_val = item.attributes.items()
            #ID 1 is the title that contains the status of the furnance.
            if item_val[0][1] == '1':
                if "Heating" in item_val[1][1].strip(' '):
                    self.status = 0
                elif "Idle" in item_val[1][1].strip(' '):
                    self.status = 1

    def get_data(self) -> dict:
        """
        Fetches data from the LOGO8 server.

        returns: A dictionary of data.
        """
        response = {}
        if self.status == 0:
            response["Status"] = "Heating"
            data = requests.post(self.url, data="MSGGET:bm,0", cookies=self.auth_cookie,
                                 timeout=30)
        else:
            response["Status"] = "Idle"
            data = requests.post(self.url, data="MSGGET:bm,1", cookies=self.auth_cookie,
                                 timeout=30)
        logging.debug(data.text)
        document = parseString(data.text)

        #The AJAX console required a different MSGGET based on the status,
        #so we need to detect the signal and set self.status accordingly.
        #When a MSGGET gets sent on the wrong status the furnace will return
        #a payload with some `t` attributes for the UI to change the titles.
        status_doc = document.getElementsByTagName("t")
        if len(status_doc) != 0:
            self._set_status(status_doc)
            return None

        for item in document.getElementsByTagName("p"):
            item_val = item.attributes.items()
            if item_val[1][1] == 'n':
                continue
            if item_val[0][1] == '0':
                response["Temperature"] = float(item_val[1][1].strip(' '))
            if item_val[0][1] == '1':
                response["o2"] = float(item_val[1][1].strip(' '))
            if item_val[0][1] == '2':
                response["Top Damper"] = float(item_val[1][1].strip(' '))
            if item_val[0][1] == '3':
                response["Bot Damper"] = float(item_val[1][1].strip(' '))
        return response