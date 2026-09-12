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
import sqlite3
import threading


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

DB_FILE = '/home/pi/concord_events.db'
RETENTION_DAYS = 30

MAX_HISTORY = 100
RECONNECT_SECONDS = 5

COMMAND_POLL_SECONDS = 0.25


KEYPRESS_STATUS = [0x0A]
KEYPRESS_FULL_STATUS = [0x0A, 0x0A]

KEYPRESS_ARM_STAY = [0x28]
KEYPRESS_ARM_AWAY = [0x27]
KEYPRESS_DISARM = [0x20]

KEYPRESS_TOGGLE_CHIME = [7, 1]


running = True
backend_instance = None

log = logging.getLogger('concord-local')


def now():
    return datetime.datetime.now().isoformat()


def safe(v):

    if isinstance(v, dict):
        return dict(
            (str(k), safe(x))
            for k, x in v.items()
        )

    if isinstance(v, (list, tuple, set)):
        return [
            safe(x)
            for x in v
        ]

    try:
        if isinstance(
            v,
            (
                str,
                unicode,
                int,
                long,
                float,
                bool
            )
        ) or v is None:
            return v

    except NameError:
        pass

    return str(v)


class Config(object):

    def __init__(self, path):

        p = ConfigParser.ConfigParser()

        p.read(path)

        if p.has_option(
            'main',
            'serialport'
        ):
            self.serialport = p.get(
                'main',
                'serialport'
            )
        else:
            self.serialport = \
                'socket://192.168.1.250:20108'

        if p.has_option(
            'main',
            'loglevel'
        ):
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

        self.arm_level_seen = False

        self.command_thread = None

        #
        # Track the first EXIT delay after an arm transition.
        # Later Extended/Twice Extended protocol cycles
        # must not restart the user-facing countdown.
        #
        self.primary_delay_pending = False
        self.primary_delay_class = None

        #
        # Protect concord_state.json atomic writes.
        # RX handler and command worker run concurrently.
        #
        self.state_write_lock = threading.RLock()

        self.state = {

            'panel': {

                'connection': 'starting',
                'state': 'starting',

                'arm_mode': 'unknown',
                'armed': False,

                'ready': None,

                'last_message': None,
                'last_refresh': None,

                'delay_active': False,
                'delay_seconds': 0,
                'delay_started': None,
                'delay_until': None,

                #
                # Concord keypad/status indicator.
                #
                'attention_required': False,
                'attention_indicator': False,
                'attention_updated': None,

                #
                # Written result returned by CHECK STATUS *
                # or FULL STATUS **.
                #
                'status_report': [],
                'status_report_type': None,
                'status_report_requested': None,
                'status_report_updated': None,

                #
                # Latest requested UI/backend command.
                #
                'last_command': None,

                'metadata': {}
            },

            'zones': {},

            'partitions': {},

            'touchpad': {},

            'alerts': [],

            'history': [],

            'system': {

                'backend': 'concord-local',

                'backend_version': '1.4',

                'serial_url': cfg.serialport,

                'started': now(),

                'updated': now()
            }
        }

        self.init_database()

        self.write()


    #
    # DATABASE
    #

    def init_database(self):

        self.db = sqlite3.connect(
            DB_FILE,
            timeout=5
        )

        self.db.execute(
            'PRAGMA journal_mode=WAL'
        )

        self.db.execute(
            'PRAGMA synchronous=NORMAL'
        )

        self.db.execute(
            'PRAGMA busy_timeout=5000'
        )

        self.db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                partition INTEGER,
                zone INTEGER,
                zone_name TEXT,
                old_state TEXT,
                new_state TEXT,
                details_json TEXT
            )
        """)

        self.db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_events_timestamp
            ON events(timestamp)
        """)

        self.db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_events_zone
            ON events(zone)
        """)

        #
        # Web -> Concord command queue.
        #
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                command TEXT NOT NULL,
                payload_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                processed_at TEXT,
                result TEXT
            )
        """)

        self.db.execute("""
            CREATE INDEX IF NOT EXISTS
            idx_commands_status
            ON commands(status, id)
        """)

        self.db.commit()

        self.cleanup_database()


    def cleanup_database(self):

        self.db.execute("""
            DELETE FROM events
            WHERE timestamp < datetime(
                'now',
                '-%d days'
            )
        """ % RETENTION_DAYS)

        #
        # Keep command audit for the same retention period.
        #
        self.db.execute("""
            DELETE FROM commands
            WHERE created_at < datetime(
                'now',
                '-%d days'
            )
        """ % RETENTION_DAYS)

        self.db.commit()


    def save_event_database(
        self,
        event_time,
        typ,
        message,
        details
    ):

        details = details or {}

        self.db.execute("""
            INSERT INTO events (
                timestamp,
                event_type,
                message,
                partition,
                zone,
                zone_name,
                old_state,
                new_state,
                details_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (

            event_time,

            typ,

            message,

            details.get(
                'partition'
            ),

            details.get(
                'zone'
            ),

            details.get(
                'zone_name'
            ),

            details.get(
                'old_state'
            ),

            details.get(
                'new_state'
            ),

            json.dumps(
                safe(details)
            )
        ))

        self.db.commit()


    #
    # STATE FILE
    #

    def write(self):

        #
        # Both the Concord RX thread and command worker
        # can write state. Serialize the temp-file +
        # rename operation so they cannot race.
        #
        self.state_write_lock.acquire()

        try:

            self.state[
                'system'
            ][
                'updated'
            ] = now()

            with open(
                STATE_TMP,
                'w'
            ) as f:

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

        finally:

            self.state_write_lock.release()


    #
    # EVENT HISTORY
    #

    def history(
        self,
        typ,
        msg,
        details=None
    ):

        event_time = now()

        e = {

            'time': event_time,

            'type': typ,

            'message': msg
        }

        if details is not None:

            e[
                'details'
            ] = safe(
                details
            )

        self.state[
            'history'
        ].insert(
            0,
            e
        )

        del self.state[
            'history'
        ][MAX_HISTORY:]

        try:

            self.save_event_database(
                event_time,
                typ,
                msg,
                details
            )

        except Exception:

            log.exception(
                'Unable to save event to SQLite'
            )


    #
    # COMMAND PROCESSING
    #

    def command_allowed(
        self,
        command,
        payload
    ):

        connection = \
            self.state[
                'panel'
            ].get(
                'connection'
            )

        if connection != 'connected':

            return (
                False,
                'Panel is not connected'
            )

        arm_mode = \
            self.state[
                'panel'
            ].get(
                'arm_mode'
            )

        if (
            command == 'chime_toggle' and
            arm_mode != 'disarmed'
        ):

            return (
                False,
                'Chime may only be changed while disarmed'
            )

        if command == 'disarm':

            if not payload.get(
                'confirmed',
                False
            ):

                return (
                    False,
                    'Disarm confirmation missing'
                )

        return (
            True,
            'OK'
        )


    def execute_command(
        self,
        command,
        payload
    ):

        allowed, reason = \
            self.command_allowed(
                command,
                payload
            )

        if not allowed:

            raise RuntimeError(
                reason
            )

        partition = int(
            payload.get(
                'partition',
                1
            )
        )

        if command == 'status':

            self.state[
                'panel'
            ][
                'status_report'
            ] = []

            self.state[
                'panel'
            ][
                'status_report_type'
            ] = 'status'

            self.state[
                'panel'
            ][
                'status_report_requested'
            ] = now()

            self.state[
                'panel'
            ][
                'status_report_updated'
            ] = now()

            self.panel.send_keypress(
                KEYPRESS_STATUS,
                partition
            )

            return (
                'Status * queued'
            )


        if command == 'full_status':

            self.state[
                'panel'
            ][
                'status_report'
            ] = []

            self.state[
                'panel'
            ][
                'status_report_type'
            ] = 'full_status'

            self.state[
                'panel'
            ][
                'status_report_requested'
            ] = now()

            self.state[
                'panel'
            ][
                'status_report_updated'
            ] = now()

            self.panel.send_keypress(
                KEYPRESS_FULL_STATUS,
                partition
            )

            return (
                'Full status ** queued'
            )


        if command == 'chime_toggle':

            self.panel.send_keypress(
                KEYPRESS_TOGGLE_CHIME,
                partition
            )

            return (
                'Chime toggle queued'
            )


        if command == 'arm_stay':

            self.panel.send_keypress(
                KEYPRESS_ARM_STAY,
                partition
            )

            return (
                'Arm Stay queued'
            )


        if command == 'arm_away':

            self.panel.send_keypress(
                KEYPRESS_ARM_AWAY,
                partition
            )

            return (
                'Arm Away queued'
            )


        if command == 'disarm':

            self.panel.send_keypress(
                KEYPRESS_DISARM,
                partition
            )

            return (
                'Disarm queued'
            )


        if command == 'refresh':

            self.panel.request_all_equipment()

            self.panel.request_dynamic_data_refresh()

            self.state[
                'panel'
            ][
                'last_refresh'
            ] = now()

            return (
                'Panel refresh queued'
            )


        raise RuntimeError(
            'Unknown command: %s'
            % command
        )


    def command_loop(self):

        log.info(
            'Command worker starting'
        )

        db = None

        try:

            db = sqlite3.connect(
                DB_FILE,
                timeout=5
            )

            db.execute(
                'PRAGMA busy_timeout=5000'
            )

            while running:

                try:

                    if (
                        self.panel is None or
                        self.state[
                            'panel'
                        ].get(
                            'connection'
                        ) != 'connected'
                    ):

                        time.sleep(
                            COMMAND_POLL_SECONDS
                        )

                        continue


                    row = db.execute("""
                        SELECT
                            id,
                            command,
                            payload_json
                        FROM commands
                        WHERE status = 'pending'
                        ORDER BY id ASC
                        LIMIT 1
                    """).fetchone()


                    if row is None:

                        time.sleep(
                            COMMAND_POLL_SECONDS
                        )

                        continue


                    command_id = int(
                        row[0]
                    )

                    command = str(
                        row[1]
                    )

                    payload_json = \
                        row[2] or '{}'


                    claimed = db.execute("""
                        UPDATE commands
                        SET status = 'processing'
                        WHERE
                            id = ?
                            AND status = 'pending'
                    """, (
                        command_id,
                    ))

                    db.commit()


                    if claimed.rowcount != 1:

                        continue


                    try:

                        payload = json.loads(
                            payload_json
                        )

                    except Exception:

                        payload = {}


                    try:

                        log.info(
                            'Processing command %d: %s',
                            command_id,
                            command
                        )

                        result = \
                            self.execute_command(
                                command,
                                payload
                            )

                        processed = now()

                        db.execute("""
                            UPDATE commands
                            SET
                                status = 'submitted',
                                processed_at = ?,
                                result = ?
                            WHERE id = ?
                        """, (
                            processed,
                            result,
                            command_id
                        ))

                        db.commit()


                        self.state[
                            'panel'
                        ][
                            'last_command'
                        ] = {

                            'id':
                                command_id,

                            'command':
                                command,

                            'status':
                                'submitted',

                            'time':
                                processed,

                            'result':
                                result
                        }

                        self.write()

                        log.info(
                            'Command %d submitted: %s',
                            command_id,
                            result
                        )


                    except Exception as e:

                        processed = now()

                        result = str(e)

                        db.execute("""
                            UPDATE commands
                            SET
                                status = 'rejected',
                                processed_at = ?,
                                result = ?
                            WHERE id = ?
                        """, (
                            processed,
                            result,
                            command_id
                        ))

                        db.commit()


                        self.state[
                            'panel'
                        ][
                            'last_command'
                        ] = {

                            'id':
                                command_id,

                            'command':
                                command,

                            'status':
                                'rejected',

                            'time':
                                processed,

                            'result':
                                result
                        }

                        self.write()

                        log.error(
                            'Command %d rejected: %s',
                            command_id,
                            result
                        )


                except Exception:

                    log.exception(
                        'Command worker problem'
                    )

                    time.sleep(
                        1
                    )


        finally:

            if db is not None:

                try:
                    db.close()
                except Exception:
                    pass

            log.info(
                'Command worker stopped'
            )


    def start_command_worker(self):

        if self.command_thread is not None:
            return

        self.command_thread = \
            threading.Thread(
                target=self.command_loop
            )

        self.command_thread.daemon = True

        self.command_thread.start()


    #
    # ZONES
    #

    def zone_state(
        self,
        raw
    ):

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

        key = \
            'zone:%s' % n

        self.state[
            'alerts'
        ] = [

            a for a
            in self.state[
                'alerts'
            ]

            if a.get(
                'key'
            ) != key
        ]

        if state in (
            'alarm',
            'faulted',
            'trouble'
        ):

            self.state[
                'alerts'
            ].insert(
                0,
                {

                    'key':
                        key,

                    'time':
                        now(),

                    'severity':
                        (
                            'critical'
                            if state == 'alarm'
                            else 'warning'
                        ),

                    'type':
                        'zone',

                    'zone':
                        n,

                    'name':
                        name,

                    'state':
                        state,

                    'raw_states':
                        safe(raw)
                }
            )


    #
    # PANEL CONNECTION
    #

    def connect(self):

        log.info(
            'Connecting via %s',
            self.cfg.serialport
        )

        self.state[
            'panel'
        ][
            'connection'
        ] = 'connecting'

        self.state[
            'panel'
        ][
            'state'
        ] = 'connecting'

        self.write()


        self.panel = \
            concord.AlarmPanelInterface(
                self.cfg.serialport,
                0.5,
                log
            )


        for code, info in \
                concord_commands.RX_COMMANDS.iteritems():

            self.panel.register_message_handler(
                info[0],
                self.handle
            )


        self.state[
            'panel'
        ][
            'connection'
        ] = 'connected'

        self.state[
            'panel'
        ][
            'state'
        ] = 'exploring'

        self.state[
            'panel'
        ][
            'last_refresh'
        ] = now()

        self.write()


        self.panel.request_all_equipment()

        self.panel.request_dynamic_data_refresh()


    def refresh(
        self,
        reason
    ):

        log.info(
            'Refreshing panel state: %s',
            reason
        )

        self.state[
            'panel'
        ][
            'state'
        ] = 'exploring'

        self.state[
            'panel'
        ][
            'last_refresh'
        ] = now()

        self.write()

        self.panel.request_all_equipment()

        self.panel.request_dynamic_data_refresh()


    #
    # RX HANDLER
    #

    def handle(
        self,
        msg
    ):

        cmd = msg.get(
            'command_id',
            'UNKNOWN'
        )


        #
        # Temporary/raw protocol visibility.
        #
        # These are the messages that will help
        # us understand the Concord STATUS *
        # behaviour precisely.
        #
        if cmd in (
            'DELAY',
            'TOUCHPAD',
            'ALARM',
            'FEAT_STATE',
            'ZONE_STATUS',
            'ARM_LEVEL'
        ):

            log.info(
                'RAW %s MESSAGE: %r',
                cmd,
                msg
            )


        self.state[
            'panel'
        ][
            'last_message'
        ] = now()


        try:

            #
            # PANEL INFORMATION
            #
            if cmd == 'PANEL_TYPE':

                md = \
                    self.state[
                        'panel'
                    ][
                        'metadata'
                    ]

                for k in (
                    'panel_type',
                    'is_concord',
                    'serial_number',
                    'hardware_revision',
                    'software_revision'
                ):

                    if k in msg:

                        md[
                            k
                        ] = safe(
                            msg[k]
                        )


            #
            # ZONE INFORMATION
            #
            elif cmd in (
                'ZONE_DATA',
                'ZONE_STATUS'
            ):

                n = int(
                    msg[
                        'zone_number'
                    ]
                )

                k = str(
                    n
                )

                raw = msg.get(
                    'zone_state',
                    []
                )


                z = \
                    self.zones_internal.get(
                        n,
                        {}
                    )

                z.update(
                    msg
                )

                z.pop(
                    'command_id',
                    None
                )

                self.zones_internal[
                    n
                ] = z


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


                new = \
                    self.zone_state(
                        raw
                    )


                old = \
                    self.state[
                        'zones'
                    ].get(
                        k,
                        {}
                    ).get(
                        'state',
                        'unknown'
                    )


                partition = int(
                    msg.get(
                        'partition_number',
                        1
                    )
                )


                self.state[
                    'zones'
                ][
                    k
                ] = {

                    'number':
                        n,

                    'partition':
                        partition,

                    'name':
                        name,

                    'state':
                        new,

                    'raw_states':
                        safe(raw),

                    'updated':
                        now()
                }


                if (
                    old != new and
                    old != 'unknown' and
                    n != 88
                ):

                    self.history(
                        'zone',

                        '%s: %s -> %s'
                        % (
                            name,
                            old,
                            new
                        ),

                        {
                            'partition':
                                partition,

                            'zone':
                                n,

                            'zone_name':
                                name,

                            'old_state':
                                old,

                            'new_state':
                                new,

                            'command':
                                cmd
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


                mode = \
                    modes.get(
                        code,
                        'unknown'
                    )


                old = \
                    self.state[
                        'panel'
                    ].get(
                        'arm_mode',
                        'unknown'
                    )


                self.arm_level_seen = True


                self.state[
                    'panel'
                ][
                    'arm_mode'
                ] = mode


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


                if mode == 'disarmed':

                    self.primary_delay_pending = False
                    self.primary_delay_class = None

                    self.state[
                        'panel'
                    ][
                        'delay_active'
                    ] = False

                    self.state[
                        'panel'
                    ][
                        'delay_seconds'
                    ] = 0

                    self.state[
                        'panel'
                    ][
                        'delay_started'
                    ] = None

                    self.state[
                        'panel'
                    ][
                        'delay_until'
                    ] = None


                if (
                    mode in (
                        'armed_stay',
                        'armed_away'
                    ) and
                    old != mode
                ):

                    self.primary_delay_pending = True
                    self.primary_delay_class = None


                part = \
                    self.state[
                        'partitions'
                    ].setdefault(
                        str(p),
                        {}
                    )


                part.update({

                    'number':
                        p,

                    'arm_mode':
                        mode,

                    'arming_level_code':
                        code,

                    'updated':
                        now()
                })


                if old != mode:

                    source = 'panel_external'

                    confirmation_map = {

                        'armed_stay': (
                            'arm_stay',
                            'Arm Stay confirmed by Concord'
                        ),

                        'armed_away': (
                            'arm_away',
                            'Arm Away confirmed by Concord'
                        ),

                        'disarmed': (
                            'disarm',
                            'Disarm confirmed by Concord'
                        )
                    }


                    expected =                         confirmation_map.get(
                            mode
                        )


                    last_command =                         self.state[
                            'panel'
                        ].get(
                            'last_command'
                        )


                    if (
                        expected is not None and
                        last_command is not None and
                        last_command.get(
                            'status'
                        ) == 'submitted' and
                        last_command.get(
                            'command'
                        ) == expected[0]
                    ):

                        confirmed = now()

                        command_id =                             int(
                                last_command[
                                    'id'
                                ]
                            )


                        self.db.execute("""
                            UPDATE commands
                            SET
                                status = 'confirmed',
                                processed_at = ?,
                                result = ?
                            WHERE
                                id = ?
                                AND status = 'submitted'
                        """, (
                            confirmed,
                            expected[1],
                            command_id
                        ))

                        self.db.commit()


                        last_command[
                            'status'
                        ] = 'confirmed'

                        last_command[
                            'time'
                        ] = confirmed

                        last_command[
                            'result'
                        ] = expected[1]


                        source = 'web_ui'


                        log.info(
                            'Command %d confirmed: %s',
                            command_id,
                            expected[1]
                        )


                    self.history(
                        'arming',

                        (
                            'System arm mode: '
                            '%s -> %s'
                        )
                        % (
                            old,
                            mode
                        ),

                        {
                            'partition':
                                p,

                            'old_state':
                                old,

                            'new_state':
                                mode,

                            'source':
                                source
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

                k = str(
                    p
                )


                d = \
                    self.parts_internal.get(
                        p,
                        {}
                    )

                d.update(
                    msg
                )

                d.pop(
                    'command_id',
                    None
                )

                self.parts_internal[
                    p
                ] = d


                part = \
                    self.state[
                        'partitions'
                    ].setdefault(
                        k,
                        {}
                    )

                part[
                    'number'
                ] = p

                part[
                    'updated'
                ] = now()


                #
                # DELAY
                #
                if cmd == 'DELAY':

                    seconds = int(
                        msg.get(
                            'delay_seconds',
                            0
                        )
                    )

                    flags = [
                        str(x)
                        for x in msg.get(
                            'delay_flags',
                            []
                        )
                    ]


                    delay_class = 'unknown'

                    for candidate in (
                        'standard',
                        'extended',
                        'twice extended'
                    ):

                        if candidate in flags:

                            delay_class = candidate

                            break


                    is_exit = (
                        'exit delay'
                        in flags
                    )

                    is_start = (
                        'start delay'
                        in flags
                    )

                    is_end = (
                        'end delay'
                        in flags
                    )


                    #
                    # Preserve latest raw protocol delay
                    # information for diagnostics.
                    #
                    self.state[
                        'panel'
                    ][
                        'protocol_delay'
                    ] = {

                        'class':
                            delay_class,

                        'direction':
                            (
                                'exit'
                                if is_exit
                                else 'entry'
                            ),

                        'phase':
                            (
                                'start'
                                if is_start
                                else
                                'end'
                                if is_end
                                else
                                'unknown'
                            ),

                        'seconds':
                            seconds,

                        'flags':
                            safe(
                                flags
                            ),

                        'time':
                            now()
                    }


                    #
                    # Only the FIRST EXIT-delay start
                    # after Stay/Away becomes the main
                    # countdown shown by the dashboard.
                    #
                    if (
                        self.primary_delay_pending and
                        is_exit and
                        is_start and
                        seconds > 0
                    ):

                        started = \
                            datetime.datetime.now()

                        until = (
                            started +
                            datetime.timedelta(
                                seconds=seconds
                            )
                        )

                        self.primary_delay_pending = False
                        self.primary_delay_class = delay_class

                        self.state[
                            'panel'
                        ][
                            'delay_active'
                        ] = True

                        self.state[
                            'panel'
                        ][
                            'delay_seconds'
                        ] = seconds

                        self.state[
                            'panel'
                        ][
                            'delay_started'
                        ] = started.isoformat()

                        self.state[
                            'panel'
                        ][
                            'delay_until'
                        ] = until.isoformat()

                        part[
                            'delay_active'
                        ] = True

                        part[
                            'delay_started'
                        ] = started.isoformat()

                        part[
                            'delay_until'
                        ] = until.isoformat()

                        log.info(
                            (
                                'Primary exit delay started: '
                                '%s / %d seconds'
                            ),
                            delay_class,
                            seconds
                        )


                    #
                    # End the dashboard countdown only
                    # when the SAME delay class ends.
                    #
                    elif (
                        is_exit and
                        is_end and
                        delay_class ==
                            self.primary_delay_class
                    ):

                        self.state[
                            'panel'
                        ][
                            'delay_active'
                        ] = False

                        self.state[
                            'panel'
                        ][
                            'delay_seconds'
                        ] = 0

                        self.state[
                            'panel'
                        ][
                            'delay_started'
                        ] = None

                        self.state[
                            'panel'
                        ][
                            'delay_until'
                        ] = None

                        part[
                            'delay_active'
                        ] = False

                        part[
                            'delay_started'
                        ] = None

                        part[
                            'delay_until'
                        ] = None

                        log.info(
                            (
                                'Primary exit delay ended: '
                                '%s'
                            ),
                            delay_class
                        )


                    #
                    # Extended/Twice Extended cycles are
                    # valid Concord protocol events but do
                    # not alter the main UI countdown.
                    #
                    else:

                        log.info(
                            (
                                'Protocol delay only: '
                                '%s / %s / %s / %d'
                            ),
                            delay_class,
                            (
                                'exit'
                                if is_exit
                                else 'entry'
                            ),
                            (
                                'start'
                                if is_start
                                else
                                'end'
                                if is_end
                                else 'unknown'
                            ),
                            seconds
                        )


                #
                # ARMING LEVEL FROM PARTITION DATA
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
                    ] = \
                        states.get(
                            code,
                            'unknown'
                        )


                    if p == 1:

                        self.state[
                            'panel'
                        ][
                            'ready'
                        ] = (
                            code == 1
                        )


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


                for fld in (
                    'user_info',
                    'feature_state',
                    'delay_flags',
                    'delay_seconds',
                    'display_text'
                ):

                    if fld in d:

                        part[
                            fld
                        ] = safe(
                            d[
                                fld
                            ]
                        )


                #
                # EXPLICIT NO DELAY
                #
                features = \
                    part.get(
                        'feature_state',
                        []
                    )


                display = str(
                    part.get(
                        'display_text',
                        ''
                    )
                ).upper()


                no_delay = (
                    'No delay' in features or
                    'NO DELAY' in display
                )


                part[
                    'no_delay'
                ] = no_delay


                if no_delay:

                    self.primary_delay_pending = False
                    self.primary_delay_class = None

                    self.state[
                        'panel'
                    ][
                        'delay_active'
                    ] = False

                    self.state[
                        'panel'
                    ][
                        'delay_seconds'
                    ] = 0

                    self.state[
                        'panel'
                    ][
                        'delay_started'
                    ] = None

                    self.state[
                        'panel'
                    ][
                        'delay_until'
                    ] = None

                    part[
                        'delay_active'
                    ] = False

                    part[
                        'delay_started'
                    ] = None

                    part[
                        'delay_until'
                    ] = None


                #
                # TOUCHPAD
                #
                if cmd == 'TOUCHPAD':

                    raw_txt = (
                        d.get(
                            'display_text'
                        ) or ''
                    )


                    #
                    # Preserve the Concord status indicator.
                    #
                    # Temporary detail screens such as
                    # SYSTEM LOW BATTERY do not contain the
                    # blinking *, so they must not clear an
                    # existing attention condition.
                    #
                    attention = (

                        '<blink>*'
                        in raw_txt

                        or

                        'PRESS STATUS'
                        in raw_txt.upper()
                    )


                    normalized_txt = ' '.join(
                        raw_txt.replace(
                            '<blink>',
                            ''
                        ).split()
                    )


                    upper_txt = normalized_txt.upper()


                    home_screen = (

                        ' P1' in upper_txt

                        or

                        upper_txt.startswith(
                            '*ARMED TO '
                        )

                        or

                        upper_txt.startswith(
                            'ARMED TO '
                        )
                    )


                    if p == 1:

                        old_attention = \
                            self.state[
                                'panel'
                            ].get(
                                'attention_required',
                                False
                            )


                        #
                        # Capture temporary status-detail
                        # screens while a * or ** request is
                        # active.
                        #
                        report_type = \
                            self.state[
                                'panel'
                            ].get(
                                'status_report_type'
                            )


                        if (
                            report_type and
                            normalized_txt and
                            not home_screen and
                            not attention
                        ):

                            report = \
                                self.state[
                                    'panel'
                                ].setdefault(
                                    'status_report',
                                    []
                                )


                            if normalized_txt not in report:

                                report.append(
                                    normalized_txt
                                )


                            self.state[
                                'panel'
                            ][
                                'status_report_updated'
                            ] = now()


                            log.info(
                                'STATUS REPORT ITEM: %s',
                                normalized_txt
                            )


                        if attention:

                            self.state[
                                'panel'
                            ][
                                'attention_required'
                            ] = True

                            self.state[
                                'panel'
                            ][
                                'attention_indicator'
                            ] = True

                            self.state[
                                'panel'
                            ][
                                'attention_updated'
                            ] = now()


                            if not old_attention:

                                log.warning(
                                    'Concord STATUS attention indicator is active'
                                )


                        elif home_screen:

                            self.state[
                                'panel'
                            ][
                                'attention_required'
                            ] = False

                            self.state[
                                'panel'
                            ][
                                'attention_indicator'
                            ] = False

                            self.state[
                                'panel'
                            ][
                                'attention_updated'
                            ] = now()


                            if old_attention:

                                log.info(
                                    'Concord STATUS attention indicator cleared'
                                )


                    txt = \
                        raw_txt.replace(
                            '<blink>',
                            ''
                        )


                    lines = \
                        txt.split(
                            '\n'
                        )


                    self.state[
                        'touchpad'
                    ][
                        k
                    ] = {

                        'partition':
                            p,

                        'line1':
                            (
                                lines[
                                    0
                                ].strip()
                                if len(
                                    lines
                                ) > 0
                                else ''
                            ),

                        'line2':
                            (
                                lines[
                                    1
                                ].strip()
                                if len(
                                    lines
                                ) > 1
                                else ''
                            ),

                        'full_text':
                            txt,

                        'raw_text':
                            raw_txt,

                        'attention_indicator':
                            bool(
                                attention
                            ),

                        'updated':
                            now()
                    }


            #
            # INITIAL DISCOVERY COMPLETE
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


                last_command =                     self.state[
                        'panel'
                    ].get(
                        'last_command'
                    )


                if (
                    last_command is not None and
                    last_command.get(
                        'command'
                    ) == 'refresh' and
                    last_command.get(
                        'status'
                    ) == 'submitted'
                ):

                    confirmed = now()

                    command_id = int(
                        last_command[
                            'id'
                        ]
                    )

                    result = (
                        'Panel refresh confirmed by Concord'
                    )


                    self.db.execute("""
                        UPDATE commands
                        SET
                            status = 'confirmed',
                            processed_at = ?,
                            result = ?
                        WHERE
                            id = ?
                            AND status = 'submitted'
                    """, (
                        confirmed,
                        result,
                        command_id
                    ))

                    self.db.commit()


                    last_command[
                        'status'
                    ] = 'confirmed'

                    last_command[
                        'time'
                    ] = confirmed

                    last_command[
                        'result'
                    ] = result


                    log.info(
                        'Command %d confirmed: %s',
                        command_id,
                        result
                    )


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


                src = \
                    msg.get(
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


                general_code = str(
                    msg.get(
                        'alarm_general_type_code',
                        ''
                    )
                )


                if general_code == '1':

                    a = {

                        'key':
                            (
                                'alarm:%s:%s:%s'
                                % (
                                    p,
                                    st,
                                    src
                                )
                            ),

                        'time':
                            now(),

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

                            'partition':
                                p,

                            'source_type':
                                st,

                            'source_number':
                                src,

                            'name':
                                name
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

                    (
                        'Panel requested refresh: %s'
                        % cmd
                    )
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


        self.write()


    #
    # RUN / SHUTDOWN
    #

    def stop(self):

        log.info(
            'Stopping Concord message loop'
        )

        try:

            if self.panel is not None:

                self.panel.stop_loop()

        except Exception:

            log.exception(
                'Unable to request Concord loop stop'
            )


    def run(self):

        self.start_command_worker()


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

                    (
                        'Concord connection fault: %s'
                        % e
                    )
                )


                self.write()


                if running:

                    time.sleep(
                        RECONNECT_SECONDS
                    )


def setup_logging(
    level
):

    log.setLevel(
        getattr(
            logging,
            level.upper(),
            logging.INFO
        )
    )


    fmt = \
        logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s'
        )


    sh = \
        logging.StreamHandler()

    sh.setFormatter(
        fmt
    )

    log.addHandler(
        sh
    )


    fh = \
        logging.handlers.RotatingFileHandler(

            '/home/pi/device-concord4/concordsvr/concordsvr.log',

            maxBytes=2000000,

            backupCount=2
        )


    fh.setFormatter(
        fmt
    )

    log.addHandler(
        fh
    )


def stop(
    sig,
    frame
):

    global running
    global backend_instance

    running = False

    log.info(
        'Shutdown signal received'
    )

    if backend_instance is not None:

        backend_instance.stop()


def main():

    global backend_instance


    path = os.path.join(

        os.path.dirname(
            os.path.abspath(
                __file__
            )
        ),

        'concordsvr.conf'
    )


    cfg = Config(
        path
    )


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


    backend_instance = \
        Backend(
            cfg
        )


    backend_instance.run()


    log.info(
        'Concord local backend stopped'
    )


if __name__ == '__main__':
    main()
