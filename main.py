import wifimgr
from   time import sleep
import machine
import gc
from machine import Timer

import mqtt_config_data
from mqtt import MQTTClient

gc.collect()

def restart_and_reconnect():
  print('Reconnecting...')
  sleep(1)
  machine.reset()
  
def set_web_server():
  try:
    print("Starting web server after 5 sec...")
    sleep(5)
    for _ in range(5):
      print('.', end='')
      web_server_started = wifimgr.set_web_server()
      if web_server_started:
        restart_and_reconnect()
  except:
    print("general exception in set_web_server")

btn_set_web_server = machine.Pin(14, machine.Pin.IN, machine.Pin.PULL_UP) #GPIO 14 -> D5 - web server activate button
# Try to check and wait 5 seconds to start web server if button pressed
if btn_set_web_server:
  sleep(5)
  set_web_server()

led_board = machine.Pin(2, machine.Pin.OUT) #GPIO 2 -> D4 # Pin is HIGH on BOOT, boot may failure if pulled LOW

started               = False
btn_manually_pressed  = False
callback_manually_set = False
is_reconnected        = False

def connect_to_wlan():
  try:
    set_ap = False
    print("Trying to connect...")
    wlan = wifimgr.get_connection(set_ap) 
    if not wlan:
      print("wlan not found and not connected.")
      return False
    print("Connected to wlan!")
    return True
  except:
    print("general exception in connect_to_wlan")
    return False

# Main Code goes here, wlan is a working network.WLAN(STA_IF) instance.
is_wlan = connect_to_wlan()
print("ESP Connected to wlan!" if is_wlan else "ESP Not connected to wlan!")

#************* MQTT *************#
gc.collect()
my_mqtt_data  = mqtt_config_data.get_data_tuple()
my_broker     = str(my_mqtt_data[0])
my_brokeruser = str(my_mqtt_data[1])
my_brokerpass = str(my_mqtt_data[2])
my_brokerport = int(my_mqtt_data[3])
my_client_id  = str(my_mqtt_data[4])
my_sub_topic  = str(my_mqtt_data[5])
my_pub_topic  = str(my_mqtt_data[6])
my_pub_status = str(my_mqtt_data[7])
my_keepalive  = int(my_mqtt_data[8])

print("Memory free:",gc.mem_free())
gc.collect()

# ######################### Get MQTT message (operational code) ##############################
def sub_cb(topic, msg):
  global started
  try:
    # If started then init message is OFF
    if started:
      print("Started first time")
      msg = b"OFF"										          
      started = False
        
    print("Get topic, message:",(topic, msg))
    try:
      mqtt_client.publish(topic=my_pub_status, msg=msg, retain=True)
      print("Published back to indicate mobile application!")
      led_On_Off.value(1) if (msg == b"ON") else led_On_Off.value(0)										  
    except Exception as e:
      print("Error in sub_cb",str(e))
  except:
    print("general exception in sub_cb exception")

def connect_and_subscribe():
  global my_client_id, my_broker, my_brokerport, my_brokeruser, my_brokerpass, my_keepalive, my_pub_status, my_sub_topic
  try:
    print("Initiate MQTTClient...")
    client = MQTTClient(client_id = my_client_id,
                        server    = my_broker,
                        port      = my_brokerport,
                        user      = my_brokeruser,
                        password  = my_brokerpass,
                        keepalive = my_keepalive)
    print("MQTTClient initiated.")
    client.set_callback(sub_cb)
    #client.settimeout = settimeout
    client.set_last_will(topic=my_pub_status, msg=b"OFFLINE", retain=True)
    print("Connecting to MQTTClient...")
    try:
      client.connect()
      client.subscribe(topic = my_sub_topic)
      print('Connected to MQTT broker: %s, subscribed to topic: %s' % (my_broker, my_sub_topic))
      print("Sending status AVLB")
      client.publish(topic=my_pub_status, msg=b"AVLB", retain=False)
    except:
      print("Mqtt broker offline, cannot connect!")
      return False
    
    return client
  except:
    print("connect_and_subscribe general exception")
    return False
  
def mqtt_reconnect(mqtt_client):
  try:
    print("mqtt_reconnect started")
    try:
      mqtt_client.disconnect()
    except:
      print("Error mqtt client disconnecting")
      sleep(0.5)
    mqtt_client = connect_and_subscribe()
    print("Client Reconnected")
    sleep(1)
    return True, mqtt_client
  except:
    print("Error mqtt client reconnecting")
    return False, mqtt_client

gc.collect()

try:
  print("Starting program...")
  mqtt_client = connect_and_subscribe()
  if is_wlan:
    print("Program started Online.")
  else:
    print("Program started Offline.")
  started = True
  led_board.value(1)
except OSError as e:
  print("OSError in starting program")
except:
  print("Other exception")
#************* END MQTT *************#

# ################## Callback for button or switch ######################
led_On_Off = machine.Pin(5, machine.Pin.OUT) #GPIO 5 -> D1
led_On_Off.value(0) # Init value off
def handle_callback(timer):
  global btn_manually_pressed, mqtt_client
  try:
    btn_manually_pressed = True
    
    if led_On_Off.value() == 1:
      led_On_Off.value(0)
      msg_on_off = b"OFF"
    else:
      led_On_Off.value(1)
      msg_on_off = b"ON" 

    try:
      mqtt_client.publish(my_pub_status, msg_on_off, retain=True)
      print("Status", msg_on_off, "published")
      btn_manually_pressed = False
    except:
      print("handle_callback error publish")

    print("Set switch ", msg_on_off)

  except:
    print("general handle_callback exception")
  
# Register a new hardware timer.
timer = Timer(0)  
def debounce(pin):
  try:
    # Start or replace a timer for 200ms, and trigger on_pressed.
    timer.init(mode=Timer.ONE_SHOT, period=200, callback=handle_callback)
  except:
    print("debounce error")

#ESP8266 callback (interrupt) pins: you can use all GPIOs, except GPIO 16. 
btn_On_Off = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_UP) #GPIO 15 -> D8 # BOOT may failure if pulled HIGH
#btn_On_Off.irq(trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING, handler=handle_callback)
btn_On_Off.irq(debounce, machine.Pin.IRQ_RISING)
 
timer1 = Timer(1)
state_on_off = b"OFF"
def read_switch_state(timer1):
  global state_on_off
  try:
    print("read_switch_state")
    mqtt_client.publish(topic=my_pub_status, msg=state_on_off, retain=True)
    led_On_Off.value(1) if (state_on_off == b"ON") else led_On_Off.value(0)
    print("Switch state",state_on_off,"sent")
  except:
    print("general error in read_switch_state")
  
# ########################### MAIN LOOP ###################################
cnt = 0
internet_alive = False
print("Main LOOP...")
while True:
  sleep(.1)
  cnt += 1
  try:
    if gc.mem_free() < 102000:
      gc.collect()

    try:
      mqtt_client.check_msg()
    except:
      try:
        print("Trying to connect to broker...")
        is_reconnected, mqtt_client = mqtt_reconnect(mqtt_client)
      except Exception as e:
        print("Broker is unavailable,",str(e))
        sleep(.5)
        gc.collect()

    if btn_manually_pressed and is_reconnected:
      # If something get wrong in mqtt or wifi connections then resend pinout status
      print("Switched manually")
      state_on_off = b"ON" if (led_On_Off.value() == 1) else b"OFF"
      btn_manually_pressed = False
      is_reconnected = False
      #Starting new timer
      timer1.init(mode=Timer.ONE_SHOT, period=300, callback=read_switch_state)

    # Every cca 2 minutes publish message that retain the connection to mqtt broker
    if cnt%530 == 0:
      try:
        cnt = 0
        mqtt_client.ping()
        mqtt_client.publish(topic=my_pub_status, msg=b"AVLB", retain=False)
      except:
        pass

  except OSError as e:
    print("General error", str(e))
  except:
    pass
    
try:
  mqtt_client.disconnect()
except:
  print("Problem disconnecting on program ends")
  
print("End program!")