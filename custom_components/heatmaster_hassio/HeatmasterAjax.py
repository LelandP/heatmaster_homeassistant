import binascii
import requests
from xml.dom.minidom import parse, parseString
    
class HeatmasterAjax():
    auth_cookie = None
    def __init__(self, ip: str, username: str="Web User", password: str="heatmaster") -> None:
        self.ip_address = ip
        self.url = f"http://{ip}/AJAX"
        self.username = username
        self.password = password
        self.status=1
        
    def login(self) -> None:
        login1 = requests.post(self.url, data="UAMCHAL:3,4,1,2,3,4")
        login1_keys = login1.text.split(',')
        login2 = requests.post(self.url,
                               data=f"UAMLOGIN:{self.username},{self._generate_password_challenge(int(login1_keys[2]))},{self._generate_server_challenge(int(login1_keys[2]))}",
                               cookies={"Security-Hint":login1_keys[1]})
        self.auth_cookie = {"Security-Hint":login2.text.split(',')[1]}
    
    def _generate_server_challenge (self, server_key: int) -> int:
        return 1 ^ 2 ^ 3 ^ 4 ^ server_key

    def _generate_password_challenge (self, server_key: int) -> int:
        password_string = f"{self.password}+{server_key}"
        crc = binascii.crc32(bytes(password_string, "utf8"))
        return crc ^ server_key
        
    def _set_status(self, status_text: list):
        for item in status_text:
            item_val = item.attributes.items()
            if item_val[0][1] == '1':
                if "Heating" in item_val[1][1].strip(' '):
                    self.status = 0
                elif "Idle" in item_val[1][1].strip(' '):
                    self.status = 1
    
    def get_data(self) -> dict:
        response = {}
        if self.status == 0:
            response["Status"] = "Heating"
            data = requests.post(self.url, data="MSGGET:bm,0", cookies=self.auth_cookie)
        else:
            response["Status"] = "Idle"
            data = requests.post(self.url, data="MSGGET:bm,1", cookies=self.auth_cookie)
        print (data.text)
        document = parseString(data.text)
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