# Qolsys Gateway - `qolsysgw`

![build](https://github.com/XaF/qolsysgw/actions/workflows/build.yaml/badge.svg)
![hacs validation](https://github.com/XaF/qolsysgw/actions/workflows/hacs-validation.yaml/badge.svg)
[![latest release](https://img.shields.io/github/v/release/XaF/qolsysgw?logo=github&sort=semver)](https://github.com/XaF/qolsysgw/releases)

Qolsys Gateway (`qolsysgw`) is an [AppDaemon][appdaemon]
automation that serves as a gateway between a Qolsys IQ Panel
([2][qolsys-panel-2], [2+][qolsys-panel-2-plus] or [4][qolsys-panel-4])
and [Home Assistant][hass]. Qolsys Gateway works by establishing a connection
to your Qolsys Panel and uses the [MQTT integration of Home Assistant][hass-mqtt].
It takes advantages of the [MQTT discovery][hass-mqtt-discovery]
feature (automatically enabled when you setup the integration) to declare the
device, alarm control panels (for each partition) and different sensors, and
keep them up to date with the information coming from the panel, while
providing you with the means to arm, disarm or trigger your alarm directly
from Home Assistant, manually or through automations.

{% if not installed -%}
## Requirements

- A Qolsys IQ Panel 2 or 2+ (software version 2.5.3 or greater), or 4
  (software version 4.1 or greater),
  for which you have the **dealer code** (defaults to `2222`). In some cases,
  the _installer code_ (defaults to `1111`) might be sufficient, but in my
  experience, it was not, as the required menus were not visible.

- Understanding that this automation is not part of the core of Home Assistant
  and is thus not officially supported by Home Assistant. By using it, you
  agree that neither Home Assistant nor myself are responsible for any issues
  with your Home Assistant configuration, loss of data, or whatever could be
  caused by using Qolsys Gateway. Setting up Qolsys Gateway requires enabling
  the Control4 protocol on your Qolsys Panel, which may open to security issues
  and someone taking over control of your alarm system, so please be aware of
  what you are doing, and only do it if you are ready to take those risks.

## Installation

You can refer to the [README](https://github.com/XaF/qolsysgw#readme) for the details of [how to install](https://github.com/XaF/qolsysgw#installation) and [how to configure](https://github.com/XaF/qolsysgw#configuration) `qolsysgw` and the different components of the process (Home Assistant, AppDaemon, MQTT and the Qolsys Panel).
{% else -%}
{% set parsed_version = version_installed.split('-')[0].replace('v', '').split('.') | map('int') | list -%}
## ChangeLog
{%   if parsed_version < [1, 6, 1] -%}
### Version 1.6.1

 * 🐛 **[bugfix]** fix: support appdaemon 4.5+ (#176)
{%   endif %}
{%   if parsed_version < [1, 6, 0] -%}
### Version 1.6.0

 * ✨ **[feature]** Add support for `Shock` sensor (#143)
{%   endif %}
{%   if parsed_version < [1, 5, 2] -%}
### Version 1.5.2

 * 🐛 **[bugfix]** fix: 🐛 add filtering to the logger override
{%   endif %}
{%   if parsed_version < [1, 5, 1] -%}
### Version 1.5.1

 * 🐛 **[bugfix]** fix: 🐛 replace accents and others when generating ids (#142)
{%   endif %}
{%   if parsed_version < [1, 5, 0] -%}
### Version 1.5.0

 * 🐛 **[bugfix]** Remove panel name as prefix of 'Last Error' sensor (#121)
 * ✨ **[feature]** Add support for `Doorbell` sensor (#115)
{%   endif %}
{%   if parsed_version < [1, 4, 0] -%}
### Version 1.4.0

 * ✨ **[feature]** Add support for `Temperature` sensor (#100)
 * ✨ **[feature]** Add support for `TakeoverModule` sensor (#110)
 * ✨ **[feature]** Add support for `Translator` sensor (#111)
 * 🐛 **[bugfix]** Sensor unique IDs deduplication when using modules (#113)
{%   endif %}
{%   if parsed_version < [1, 3, 0] -%}
### Version 1.3.0

 * ♻️ **[refactor]** disabling 'Panel Glass Break' sensor as it is not receiving updates (#88)
 * 🗑️ **[cleanup]** remove redundant code in sensor classes (#89)
 * ✨ **[feature]** Add support for `Keypad` sensors (#90)
 * ✨ **[feature]** Add support for `Auxiliary Pendant` sensors (#91)
 * ✨ **[feature]** Add support for `Siren` sensors (#92)
 * ✨ **[feature]** Add support for `KeyFob` sensors (#93)
 * 🐛 **[bugfix]** change sensors unique IDs to be recognized upon reinstall (#95)
{%   endif %}
{%   if parsed_version < [1, 2, 0] -%}
### Version 1.2.0

 * ✨ **[feature]** Add support for tampered sensors (#74)
 * 🐛 **[bugfix]** Add support for `ARM-STAY-EXIT-DELAY` partition state
 * ✨ **[feature]** Add support for `Tilt` sensors (#78)
 * 🐛 **[bugfix]** handle properly when to require a user code from HA (#81)
{%   endif %}
{%   if parsed_version < [1, 1, 0] -%}
### Version 1.1.0

 * ✨ **[feature]** Add `last_error_type` and `last_error_desc` attributes to partitions (#60)
 * ✨ **[feature]** Add `disarm_failed` counter as partition attribute (#61)
 * ♻️ **[refactor]** deduplicate code in the ARM control classes (#62)
 * ✨ **[feature]** Add support for `bypass` parameter when arming (#63)
 * 🐛 **[bugfix]** Control commands weren't reading the `delay` and `bypass` parameters (#66)
 * ✨ **[feature]** Add `qolsysgw` error sensor (#68)
 * 🐛 **[bugfix]** config parameters shouldn't be overriden by 'None' values (#69)
 * ♻️ **[refactor]** centralize the generation of the device payload (#70)
 * ♻️ **[refactor]** move mac address resolution to avoid duplication (#71)
 * ✨ **[feature]** disable by default entities that do not update (#72)
{%   endif %}
{%   if parsed_version < [1, 0, 0] -%}
### Version 1.0.0

This is the first official version of `qolsysgw`, which will now have release numbers.
This release includes all commits up to this point, and will allow to provide an easy
and simple changelog when making new releases.
{%   endif %}
{% endif -%}


<!--
List of links used in that page, sorted alphabetically by tag
-->
[appdaemon]: https://github.com/AppDaemon/appdaemon
[hass-mqtt-discovery]: https://www.home-assistant.io/docs/mqtt/discovery/
[hass-mqtt]: https://www.home-assistant.io/integrations/mqtt/
[hass]: https://www.home-assistant.io/
[qolsys-panel-2]: https://qolsys.com/iq-panel-2/
[qolsys-panel-2-plus]: https://qolsys.com/iq-panel-2-plus/
[qolsys-panel-4]: https://qolsys.com/iq-panel-4/
