# Heatmaster integration for home assistant

This integration is for monitoring your heatmaster boiler with siemens LOGO controllers.


## Getting Started

### Dependencies

You must have HACS installed on your homeassistant, you can follow this [install guide](https://hacs.xyz/docs/setup/download/).

### Installing

Currently this integration is not part of the default list in HACS so you will need to add the repo manually.

* Open HACS menu
* Select integrations option
* Open the kebab menu at the top right and select `Custom Repositories`
* Paste `https://github.com/LelandP/heatmaster_homeassistant` in the repository feild
* Select `integration` for Category
* Finally Click ADD

Once Home Assistant restarts you will need to add the following to your `Configuration.yaml`
```
sensor:
  - platform: heatmaster_hassio
    ip: <IP Address Here>
```
