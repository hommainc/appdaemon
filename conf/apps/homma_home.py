import urllib.request
import json
import re

class HommaHome:
    """Representation of a Homma Home"""

    def __init__(self, home_id, session_token):
        self._home_id = home_id
        self._session_token = session_token


        self._devices = self.__get_devices(session_token)

    def __get_devices(self, session_token):
        try:
            api_url = 'https://api-stage.homma.io/devices'
            req = urllib.request.Request(api_url,
                                         headers={'X-Auth-Token': session_token})

            response = urllib.request.urlopen(req)
            data = response.read()
            devices = json.loads(data.decode('utf-8'))

        except:
            print('HTTP Request failed')

        return devices

    @property
    def devices(self):
        return self._devices

    @property
    def home_id(self):
        return self._home_id

    def entity(self, device_id):
        for d in self._devices:
            if d['id'] == device_id:
                return d['entity_id']
    
    def is_type_of(self, type, node_id):
        for d in self._devices:
            if d['zwave_node'] == node_id and d['type'] == type:
                return True
        else:
            return False

    def get_device_by(self, field, value):
        for d in self._devices:
            if d[field] == value:
                return d
        else:
            return None

    def get_sensor_metric_type(self, ha_entity_id):
        m = re.search('burglar|alarm|luminance|temperature|relative_humidity|ultraviolet|battery|door_window_sensor', ha_entity_id)
        if m == None:
            return None
        else:
            return m.group(0)
