#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import time
import json
import signal
import logging
import logging.handlers
import datetime
import ConfigParser

from concord import concord, concord_commands
from concord.concord_commands import (
    TRIPPED,
    FAULTED,
    ALARM,
    TROUBLE,
    BYPASSED
)


STATE_FILE = '/home/pi/concord_state.json'
STATE_TMP = STATE_FILE + '.tmp'

MAX_HISTORY = 100
RECONNECT_SECONDS = 5

running = True

log = logging.getLogger('concord-local')


def now():
    return datetime.datetime.now().isoformat()


def safe(v):
    if isinstance(v, dict):
        return dict((str(k), safe(x)) for k, x in v.items())

    if isinstance(v, (list, tuple, set)):
        return [safe(x) for x in v]

    try:
        if isinstance(
            v,
            (str, unicode, int, long, float, bool)
        ) or v is None:
            return v
    except NameError:
        pass

    return str(v)


class Config(object):

    def __init__(self, path):

        p = ConfigParser.ConfigParser()
        p.read(path)

        if p.has_option('main', 'serialport'):
            self.serialport = p.get(
                'main',
                'serialport'
            )
        else:
            self.serialport = \
                'socket://192.168.1.250:20108'

        if p.has_option('main', 'loglevel'):
            self.loglevel = p.get(
                'main',
                'loglevel'
            )
        else:
            self.loglevel = 'INFO'


class Backend(object):

    def __init__(self, cfg):

        self.cfg = cfg
        self.panel = None

        self.zones_internal = {}
        self.parts_internal = {}

        #
        # Important:
        #
        # PART_DATA may establish initial state after startup.
        #
        # Once a real ARM_LEVEL message has been seen,
        # ARM_LEVEL becomes authoritative for live
        # ARM/DISARM state.
        #
        self.arm_level_seen = False

        self.state = {

            'panel': {
                'connection': 'starting',
                'state': 'starting',

                'arm_mode': 'unknown',
                'armed': False,

                'ready': None,

                'last_message': None,
                'last_refresh': None,

                'metadata': {}
            },

            'zones': {},

            'partitions': {},

            'touchpad': {},

            'alerts': [],

            'history': [],

            'system': {
                'backend': 'concord-local',
                'backend_version': '1.1',
                'serial_url': cfg.serialport,
                'started': now(),
                'updated': now()
            }
        }

        self.write()


    def write(self):

        self.state['system']['updated'] = now()

        with open(STATE_TMP, 'w') as f:
            json.dump(
                safe(self.state),
                f,
                indent=2,
                sort_keys=True
            )

        os.rename(
            STATE_TMP,
            STATE_FILE
        )


    def history(
        self,
        typ,
        msg,
        details=None
    ):

        e = {
            'time': now(),
            'type': typ,
            'message': msg
        }

        if details is not None:
            e['details'] = safe(details)

        self.state['history'].insert(
            0,
            e
        )

        del self.state['history'][MAX_HISTORY:]


    def zone_state(self, raw):

        if raw is None:
            return 'unknown'

        if ALARM in raw:
            return 'alarm'

        if TROUBLE in raw:
            return 'trouble'

        if FAULTED in raw:
            return 'faulted'

        if BYPASSED in raw:
            return 'bypassed'

        if TRIPPED in raw:
            return 'open'

        if len(raw) == 0:
            return 'closed'

        return 'unavailable'


    def alert_for_zone(
        self,
        n,
        name,
        state,
        raw
    ):

        key = 'zone:%s' % n

        #
        # Remove previous alert for this zone.
        #
        self.state['alerts'] = [
            a for a in self.state['alerts']
            if a.get('key') != key
        ]

        #
        # Only actual abnormal zone conditions
        # become alerts.
        #
        if state in (
            'alarm',
            'faulted',
            'trouble'
        ):

            self.state['alerts'].insert(
                0,
                {
                    'key': key,
                    'time': now(),

                    'severity':
                        'critical'
                        if state == 'alarm'
                        else 'warning',

                    'type': 'zone',

                    'zone': n,
                    'name': name,

                    'state': state,

                    'raw_states': safe(raw)
                }
            )


    def connect(self):

        log.info(
            'Connecting via %s',
            self.cfg.serialport
        )

        self.state['panel']['connection'] = \
            'connecting'

        self.state['panel']['state'] = \
            'connecting'

        self.write()

        self.panel = concord.AlarmPanelInterface(
            self.cfg.serialport,
            0.5,
            log
        )

        #
        # Register every RX command from
        # py-concord with our message handler.
        #
        for code, info in \
                concord_commands.RX_COMMANDS.iteritems():

            self.panel.register_message_handler(
                info[0],
                self.handle
            )

        self.state['panel']['connection'] = \
            'connected'

        self.state['panel']['state'] = \
            'exploring'

        self.state['panel']['last_refresh'] = \
            now()

        self.write()

        #
        # Ask Concord for the current image/state.
        #
        self.panel.request_all_equipment()
        self.panel.request_dynamic_data_refresh()


    def refresh(self, reason):

        log.info(
            'Refreshing panel state: %s',
            reason
        )

        self.state['panel']['state'] = \
            'exploring'

        self.state['panel']['last_refresh'] = \
            now()

        self.write()

        self.panel.request_all_equipment()
        self.panel.request_dynamic_data_refresh()


    def handle(self, msg):

        cmd = msg.get(
            'command_id',
            'UNKNOWN'
        )

        self.state['panel']['last_message'] = \
            now()

        try:

            #
            # PANEL INFORMATION
            #
            if cmd == 'PANEL_TYPE':

                md = \
                    self.state['panel']['metadata']

                for k in (
                    'panel_type',
                    'is_concord',
                    'serial_number',
                    'hardware_revision',
                    'software_revision'
                ):

                    if k in msg:
                        md[k] = safe(msg[k])


            #
            # ZONE INFORMATION
            #
            elif cmd in (
                'ZONE_DATA',
                'ZONE_STATUS'
            ):

                n = int(
                    msg['zone_number']
                )

                k = str(n)

                raw = msg.get(
                    'zone_state',
                    []
                )

                z = self.zones_internal.get(
                    n,
                    {}
                )

                z.update(msg)

                z.pop(
                    'command_id',
                    None
                )

                self.zones_internal[n] = z

                name = (
                    z.get(
                        'zone_text'
                    ) or ''
                ).strip()

                if not name:

                    if n == 88:
                        name = 'UNKNOWN_88'
                    else:
                        name = \
                            'Zone %s' % n

                new = self.zone_state(
                    raw
                )

                old = \
                    self.state['zones'].get(
                        k,
                        {}
                    ).get(
                        'state',
                        'unknown'
                    )

                self.state['zones'][k] = {
                    'number': n,

                    'partition': int(
                        msg.get(
                            'partition_number',
                            1
                        )
                    ),

                    'name': name,

                    'state': new,

                    'raw_states': safe(raw),

                    'updated': now()
                }

                if old != new:

                    self.history(
                        'zone',

                        '%s: %s -> %s' % (
                            name,
                            old,
                            new
                        ),

                        {
                            'zone': n,
                            'command': cmd
                        }
                    )

                self.alert_for_zone(
                    n,
                    name,
                    new,
                    raw
                )

                log.info(
                    "Zone %d - %r | State: %s",
                    n,
                    name,
                    new
                )


            #
            # LIVE ARM / DISARM STATE
            #
            # This is authoritative once received.
            #
            elif cmd == 'ARM_LEVEL':

                code = int(
                    msg.get(
                        'arming_level_code',
                        -1
                    )
                )

                p = int(
                    msg.get(
                        'partition_number',
                        1
                    )
                )

                modes = {
                    0: 'zone_test',
                    1: 'disarmed',
                    2: 'armed_stay',
                    3: 'armed_away',
                    4: 'armed_night',
                    5: 'armed_silent',
                    8: 'phone_test',
                    9: 'sensor_test'
                }

                mode = modes.get(
                    code,
                    'unknown'
                )

                old = \
                    self.state['panel'].get(
                        'arm_mode',
                        'unknown'
                    )

                #
                # ARM_LEVEL becomes authoritative.
                #
                self.arm_level_seen = True

                self.state['panel']['arm_mode'] = \
                    mode

                self.state['panel']['armed'] = \
                    code in (
                        2,
                        3,
                        4,
                        5
                    )

                #
                # Keep Partition structure updated too.
                #
                part = \
                    self.state['partitions'].setdefault(
                        str(p),
                        {}
                    )

                part.update({
                    'number': p,
                    'arm_mode': mode,
                    'arming_level_code': code,
                    'updated': now()
                })

                if old != mode:

                    self.history(
                        'arming',

                        'System arm mode: %s -> %s' % (
                            old,
                            mode
                        ),

                        {
                            'partition': p
                        }
                    )

                log.info(
                    'System arm mode: %s',
                    mode
                )


            #
            # PARTITION / FEATURE / DELAY /
            # TOUCHPAD INFORMATION
            #
            elif cmd in (
                'PART_DATA',
                'FEAT_STATE',
                'DELAY',
                'TOUCHPAD'
            ):

                p = int(
                    msg.get(
                        'partition_number',
                        1
                    )
                )

                k = str(p)

                d = self.parts_internal.get(
                    p,
                    {}
                )

                d.update(msg)

                d.pop(
                    'command_id',
                    None
                )

                self.parts_internal[p] = d

                part = \
                    self.state['partitions'].setdefault(
                        k,
                        {}
                    )

                part['number'] = p
                part['updated'] = now()


                #
                # PART_DATA ARMING INFORMATION
                #
                if 'arming_level_code' in d:

                    code = int(
                        d.get(
                            'arming_level_code',
                            -1
                        )
                    )

                    states = {
                        -1: 'unknown',
                        0: 'zone_test',
                        1: 'ready',
                        2: 'stay',
                        3: 'away',
                        4: 'night',
                        5: 'silent',
                        8: 'phone_test',
                        9: 'sensor_test'
                    }

                    part[
                        'arming_level_code'
                    ] = code

                    part[
                        'state'
                    ] = states.get(
                        code,
                        'unknown'
                    )


                    #
                    # Partition 1 is our actual home
                    # security partition.
                    #
                    if p == 1:

                        self.state[
                            'panel'
                        ][
                            'ready'
                        ] = (
                            code == 1
                        )

                        #
                        # IMPORTANT:
                        #
                        # PART_DATA may initialize the
                        # arm state after backend startup.
                        #
                        # After we have received ARM_LEVEL,
                        # PART_DATA is NEVER allowed to
                        # overwrite live ARM/DISARM state.
                        #
                        if not self.arm_level_seen:

                            modes = {
                                0: 'zone_test',
                                1: 'disarmed',
                                2: 'armed_stay',
                                3: 'armed_away',
                                4: 'armed_night',
                                5: 'armed_silent',
                                8: 'phone_test',
                                9: 'sensor_test'
                            }

                            part_mode = \
                                modes.get(
                                    code,
                                    'unknown'
                                )

                            self.state[
                                'panel'
                            ][
                                'arm_mode'
                            ] = part_mode

                            self.state[
                                'panel'
                            ][
                                'armed'
                            ] = code in (
                                2,
                                3,
                                4,
                                5
                            )

                            log.info(
                                'Initial partition arm mode: %s',
                                part_mode
                            )


                #
                # Copy useful partition information.
                #
                for fld in (
                    'user_info',
                    'feature_state',
                    'delay_flags',
                    'delay_seconds',
                    'display_text'
                ):

                    if fld in d:
                        part[fld] = \
                            safe(d[fld])


                #
                # TOUCHPAD DISPLAY
                #
                if cmd == 'TOUCHPAD':

                    txt = (
                        d.get(
                            'display_text'
                        ) or ''
                    ).replace(
                        '<blink>',
                        ''
                    )

                    lines = txt.split(
                        '\n'
                    )

                    self.state[
                        'touchpad'
                    ][k] = {

                        'partition': p,

                        'line1':
                            lines[0].strip()
                            if len(lines) > 0
                            else '',

                        'line2':
                            lines[1].strip()
                            if len(lines) > 1
                            else '',

                        'full_text': txt,

                        'updated': now()
                    }


            #
            # INITIAL EQUIPMENT DISCOVERY COMPLETE
            #
            elif cmd == 'EQPT_LIST_DONE':

                self.state[
                    'panel'
                ][
                    'state'
                ] = 'active'

                self.state[
                    'panel'
                ][
                    'connection'
                ] = 'connected'

                log.info(
                    'Panel state is active'
                )


            #
            # ALARM-FORMAT EVENT
            #
            elif cmd == 'ALARM':

                p = int(
                    msg.get(
                        'partition_number',
                        1
                    )
                )

                src = msg.get(
                    'source_number'
                )

                st = str(
                    msg.get(
                        'source_type',
                        'Unknown'
                    )
                )

                desc = str(
                    msg.get(
                        'alarm_general_type',
                        'Alarm'
                    )
                )

                if msg.get(
                    'alarm_specific_type'
                ):

                    desc += \
                        ' / ' + str(
                            msg.get(
                                'alarm_specific_type'
                            )
                        )

                name = ''

                if src is not None:

                    name = \
                        self.state[
                            'zones'
                        ].get(
                            str(src),
                            {}
                        ).get(
                            'name',
                            ''
                        )


                #
                # Concord sends many ALARM-format
                # events that are informational.
                #
                # Only general type 1 is treated
                # as an actual alarm/trouble event.
                #
                general_code = str(
                    msg.get(
                        'alarm_general_type_code',
                        ''
                    )
                )


                if general_code == '1':

                    a = {
                        'key':
                            'alarm:%s:%s:%s' % (
                                p,
                                st,
                                src
                            ),

                        'time': now(),

                        'severity':
                            'critical',

                        'type':
                            'alarm',

                        'partition':
                            p,

                        'source_type':
                            st,

                        'source_number':
                            src,

                        'name':
                            name,

                        'description':
                            desc
                    }

                    self.state[
                        'alerts'
                    ].insert(
                        0,
                        a
                    )

                    self.state[
                        'alerts'
                    ] = \
                        self.state[
                            'alerts'
                        ][:25]

                    self.state[
                        'panel'
                    ][
                        'state'
                    ] = 'alarm'

                    self.history(
                        'alarm',
                        desc,
                        a
                    )

                    log.error(
                        'ALARM: %s',
                        desc
                    )

                else:

                    self.history(
                        'event',
                        desc,
                        {
                            'partition': p,
                            'source_type': st,
                            'source_number': src,
                            'name': name
                        }
                    )

                    log.info(
                        'Panel event: %s',
                        desc
                    )


            #
            # PANEL REQUESTED REFRESH
            #
            elif cmd in (
                'CLEAR_IMAGE',
                'EVENT_LOST'
            ):

                self.history(
                    'system',
                    'Panel requested refresh: %s' %
                    cmd
                )

                self.write()

                self.refresh(
                    cmd
                )

                return


        except Exception:

            log.exception(
                'Problem processing %s: %r',
                cmd,
                msg
            )


        #
        # Publish every processed change.
        #
        self.write()


    def run(self):

        while running:

            try:

                self.connect()

                self.panel.message_loop()

                if running:
                    raise RuntimeError(
                        'Concord message loop ended'
                    )

            except KeyboardInterrupt:

                break

            except Exception as e:

                log.exception(
                    'Concord connection failed: %s',
                    e
                )

                self.state[
                    'panel'
                ][
                    'connection'
                ] = 'faulted'

                self.state[
                    'panel'
                ][
                    'state'
                ] = 'faulted'

                self.history(
                    'system',
                    'Concord connection fault: %s' %
                    e
                )

                self.write()

                if running:
                    time.sleep(
                        RECONNECT_SECONDS
                    )


def setup_logging(level):

    log.setLevel(
        getattr(
            logging,
            level.upper(),
            logging.INFO
        )
    )

    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s'
    )

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    log.addHandler(sh)

    fh = \
        logging.handlers.RotatingFileHandler(
            '/home/pi/device-concord4/concordsvr/concordsvr.log',
            maxBytes=2000000,
            backupCount=2
        )

    fh.setFormatter(fmt)
    log.addHandler(fh)


def stop(sig, frame):

    global running

    running = False

    log.info(
        'Shutdown signal received'
    )


def main():

    path = os.path.join(
        os.path.dirname(
            os.path.abspath(
                __file__
            )
        ),
        'concordsvr.conf'
    )

    cfg = Config(path)

    setup_logging(
        cfg.loglevel
    )

    signal.signal(
        signal.SIGTERM,
        stop
    )

    signal.signal(
        signal.SIGINT,
        stop
    )

    log.info(
        'Concord local backend starting'
    )

    Backend(cfg).run()

    log.info(
        'Concord local backend stopped'
    )


if __name__ == '__main__':
    main()
