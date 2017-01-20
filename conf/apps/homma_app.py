import appdaemon.appapi as appapi
import paho.mqtt.client as mqtt
import homma_home as homma
import re

#
# App to publish scene and sensor events
#
# Args:
#
#mqtt_host = _
#mqtt_username = _
#mqtt_password = _
#mqtt_port = _
#home_id = user's Homma home ID
#session_id = for auth (using session_id for now)
#
# Release Notes
#
# Version 1.0:
#   Initial Version

class HommaApp(appapi.AppDaemon):

  entity_topic_map = {
    'temperature': 'temperature',
    'luminance': 'lux',
    'ultraviolet': 'uv',
    'battery': 'battery',
    'alarm': 'alarm',
    'relative_humidity': 'humidity',
    'door_window_sensor': 'contact'
  }

  uuidx ='[0-9A-F]{8}-[0-9A-F]{4}-4[0-9A-F]{3}-[89AB][0-9A-F]{3}-[0-9A-F]{12}'

  def initialize(self):
    #get home and devices data
    self.home = homma.HommaHome(self.args['home_id'], self.args['session_id'])

    self.log(self.home.devices)

    self.setup_mqtt()
    
    self.listen_event(self.zwave_scene_event, "zwave.scene_activated")
    self.listen_event(self.node_event, "state_changed")

  def on_connect(self, client, userdata, flags, rc):
    self.log(("Connected with result code " + str(rc)))
    client.subscribe("/site/{}/rooms/+/+/+/control".format(self.home.home_id))

  def on_disconnect(self, client, userdata, flags, rc):
    self.log("DISCONNECTED FROM MQTT")

  def on_message(self, client, userdata, msg):
    self.log("new message: " + msg.topic + " " + msg.payload.decode('utf-8'))

    control_pattern = re.compile("(?i)/site/{}/rooms/{}/(switches|dimmers)/{}/control".format(self.args['home_id'], self.uuidx, self.uuidx))

    if control_pattern.match(msg.topic) == None:
      self.log("RECEIVED AN INVALID TOPIC")
      return None

    #get device ID from topic
    topic_words = str.split(msg.topic, "/")
    device_id = topic_words[6]
    entity_id = self.home.entity(device_id)
    handle_type = topic_words[5]
    self.log(handle_type)

    if handle_type == "switches":
      self.switch_message_received(entity_id, msg.payload.decode('utf-8'))
    elif handle_type == "dimmers":
      self.dimmer_message_received(entity_id, msg.payload.decode('utf-8'))

  def setup_mqtt(self):
    client = mqtt.Client()
    client.username_pw_set(self.args['mqtt_username'], self.args['mqtt_password'])
    client.on_connect = self.on_connect
    client.on_message = self.on_message
    client.on_disconnect = self.on_disconnect

    print("connecting to mqtt...")

    client.connect(self.args['mqtt_host'], int(self.args['mqtt_port']), 300)
    client.loop_start()

    self._mqtt_client = client

  def rescale_light_value(X,A,B,C,D):
      retval = ((float(X - A) / (B - A)) * (D - C)) + C
      return int(round(retval))

  # Called when we get a switch message
  def switch_message_received(self, entity_id, payload):
      if not entity_id:
        return

      """Processing MQTT Switch Message"""
      self.log("Processing MQTT Switch Message: entity_id = {}, payload = {}".format(entity_id, payload))
      
      # hass.states.set(entity_id, payload)
      if payload == "1":
         self.turn_on(entity_id)
      if payload == "0":
         self.turn_off(entity_id)

  # Called when we get a dimmer message
  def dimmer_message_received(self, entity_id, payload):
      if not entity_id:
        return
      """Processing MQTT Dimmer Message"""
      self.log("Processing MQTT Dimmer Message")
      
      #hass.states.set(entity_id, payload)
      if payload == "0":
          self.turn_off(entity_id)
      else:
          payload = rescale_light_value(int(payload),0,100,0,255)
          self.turn_on(entity_id, brightness=payload)

  def node_event(self, event_name, data, kwargs):
    # self.log("Event: {}, data = {}, kwargs = {}".format(event_name, data, kwargs))

    state = data['new_state']['state']
    node_id = data['new_state']['attributes'].get('node_id')
    unit = data['new_state']['attributes'].get('unit_of_measurement')
    entity_id = data['new_state']['entity_id']

    # self.log("NODE ID: {}, UNIT OF MEASUREMENT: {}, VALUE: {}".format(node_id, unit, state))

    if node_id == None:
        return None

    device = self.home.get_device_by('zwave_node', node_id)
    metric_type = self.home.get_sensor_metric_type(entity_id)

    if self.home.is_type_of("multisensor", node_id) == True:
        self.log("publishing sensor metric: {}, {}".format(metric_type, state))

        if metric_type == "burglar":
            if state == "8":
                payload = "ON"
            else:
                payload = "OFF"
            self._mqtt_client.publish("/site/{}/rooms/{}/sensors/{}/motion".format(self.home.home_id, device['room_id'], device['id']), payload, 1, True)
            
        if metric_type in ['temperature', 'relative_humidity', 'luminance', 'ultraviolet', 'battery']:
            self._mqtt_client.publish("/site/{}/rooms/{}/sensors/{}/{}".format(self.home.home_id, device['room_id'], device['id'], self.entity_topic_map[metric_type]), state, 1, True)

        return True
    elif self.home.is_type_of("contact", node_id) == True:
        if state == "on":
            payload = "OPEN"
        else:
            payload = "CLOSED"
        
        self._mqtt_client.publish("/site/{}/rooms/{}/contacts/{}".format(self.home.home_id, device['room_id'], device['id']), payload, 1, True)
    elif self.home.is_type_of("switch", node_id) == True:
       if unit == 'W':
           metric_word = 'watts'
       elif unit == 'kWh':
           metric_word = 'kwh'
       elif unit == 'V':
           metric_word = 'volts'
       elif unit == 'A':
           metric_word = 'amps'
       else:
           return
          
       self.log("publishing switch metric: {}, {}".format(unit, state))
       self._mqtt_client.publish("/site/{}/rooms/{}/switches/{}/{}".format(self.home.home_id, device['room_id'], device['id'], metric_word), state, 1, True)
    
  def zwave_scene_event(self, event_name, data, kwargs):
    self.log("Event: {}, data = {}, args = {}".format(event_name, data, kwargs))

    remote = self.home.get_device_by('entity_id', data['entity_id'])
    self.log(remote)

    if remote == None:
      return
    
    self._mqtt_client.publish("/site/{}/rooms/{}/remotes/{}".format(self.home.home_id, remote['room_id'], remote['id']), data['scene_id'])