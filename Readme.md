# RCS HVAC Controller

## Zone Configuration.

The command line parameter, `--config`, specifies full path to a configuration file that specifies the name and index of each zone.  The config file should reflect the actual hardware configuration, and it does not control the actual hardware.

This file is formated as YAML with a `.yml` extension.  

The basic format is like this:

```yaml
---
device_node_id: "montana_rcs_zrc6"
zones:
    - name: "Bedroom Thermostat"
      index: 2
    - name: "Great Room Thermostat"
      index: 3
    - name: "Office Thermostat"
      index: 1
```
Zone indexes are numbered starting with 1 and each name must be unique within the configuration.  Zone names can contain only letters, numbers and spaces.   Where it is necessary to convert a zone name into an entity, spaces will be represented as underscores.

## MQTT Device Discovery

The documentation for Home Assistant MQTT discover is: 

- [here](https://www.home-assistant.io/integrations/mqtt/).
- [here](https://www.home-assistant.io/integrations/climate.mqtt/)

To enable MQTT discovery in Home Assistant, one must publish a special configuration message to a specific topic that Home Assistant listens to for discovering new devices. The topic usually follows the pattern `homeassistant/[component]/[node_id]/[object_id]/config`, where:

- `[component]` is the type of the Home Assistant component (e.g., `climate` for an HVAC controller).
- `[node_id]` is a unique identifier for your device.
- `[object_id]` is the identifier for the specific object or sensor on the device.

Since we're dealing with an HVAC controller, we are using the `climate` component. The JSON payload for the configuration message should contain at least the following fields:

- `name`: Friendly name of the climate device.
- `unique_id`: A unique identifier for the device.
- `command_topic`: The MQTT topic to publish commands to control the HVAC.
- `state_topic`: The MQTT topic where the device publishes its state.
- `temperature_command_topic`: The MQTT topic to publish temperature setpoint commands if applicable.
- `temperature_state_topic`: The MQTT topic where the device publishes its current temperature.
- `mode_command_topic`: The MQTT topic to publish mode commands (e.g., "heat", "cool", "auto").
- `mode_state_topic`: The MQTT topic where the device publishes its current mode.

Here's an example of the JSON payload:

```json
{
  "name": "Living Room Thermostat",
  "device_class": "climate",
  "unique_id": "montana_great_room_thermostat",
  "device": {
    "identifiers": "montana_great_room_thermostat",
    "name": "ZC6R HVAC Controller - Living room zone"
  },
  "modes": ["off", "heat", "cool", "auto"],
  "preset_modes": ["away", "sleep", "home"],
  "optimistic": false,
  "precision": 1.0,
  "temp_step": 1.0,
  "~": "homeassistant/climate/montana_zc6r/great_room_temperature",
  "availability_topic": "homeassistant/climate/montana_rc6r/availability",
  "action_topic": "~/current_action",
  "temperature_command_topic": "~/set_temperature",
  "temperature_state_topic": "~/current_setpoint",
  "mode_command_topic": "~/set_mode",
  "mode_state_topic": "~/mode"
}
```

- `action_topic` string (optional): The MQTT topic to subscribe for changes of the current action. If this is set, the climate graph uses the value received as data source. Valid values: `off`, `heating`, `cooling`, `drying`, `idle`, `fan`.

You should adjust the topics and payload to match your device's capabilities. Once you've formed the correct JSON payload, publish it to the corresponding discovery topic. For example, if your `node_id` is `zc6r_hvac` and your `object_id` is `great_room`, the topic would be:

`homeassistant/climate/montana_zc6r/great_room_thermostat/config`

Remember to retain the message on the broker so that it persists across restarts of Home Assistant or the MQTT broker. In Python using paho-mqtt, you'll set the `retain=True` parameter in the `publish` method.

Keep in mind that the exact JSON structure can vary depending on the specific capabilities of your HVAC controller and how you wish to integrate it with Home Assistant. You should refer to the [MQTT Climate](https://www.home-assistant.io/integrations/climate.mqtt/) component documentation in Home Assistant for all configurable options and ensure that your JSON payload adheres to the requirements.

